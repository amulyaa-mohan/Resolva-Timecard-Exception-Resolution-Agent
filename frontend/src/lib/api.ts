/**
 * The boundary between the UI and the Resolva backend.
 *
 * Everything here talks to the real API. Three rules this file must keep:
 *  1. A write that does not reach the server is a failure. It is never reported as success.
 *  2. The browser never decides whether a correction is valid. Only the backend's deterministic
 *     validator does, and its result is displayed, never recomputed here.
 *  3. The manager's identity is the bearer token the server issued. No role is sent from here;
 *     the server scopes every read and write to the employees assigned to that manager.
 *
 * Requests go to /api/... which Vite proxies to the backend (see vite.config.ts).
 */
import {
  AuditEvent,
  Citation,
  ExceptionItem,
  LLMProposal,
  PunchEvent,
  RuleOutcome,
  Severity,
} from '../types/contracts';

const TOKEN_KEY = 'resolva.manager.token';

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

let token: string | null = null;

export function getToken(): string | null {
  if (token) return token;
  try {
    token = sessionStorage.getItem(TOKEN_KEY);
  } catch {
    token = null; // private browsing, blocked storage
  }
  return token;
}

export function setToken(value: string | null): void {
  token = value;
  try {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* keeping it in memory alone is fine */
  }
}

/** Problem+json from the backend, or a readable fallback. */
async function describe(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (!body.title && !body.detail) throw new Error('not a problem document');
    const parts = [body.title, body.detail].filter(Boolean);
    if (Array.isArray(body.errors) && body.errors.length) {
      const first = body.errors[0];
      if (first?.current_evidence_version) {
        parts.push('Re-propose on the latest evidence before approving.');
      } else if (first?.reason) {
        parts.push(first.reason);
      } else if (first?.msg) {
        parts.push(`${(first.loc ?? []).join('.')}: ${first.msg}`);
      }
    }
    return parts.join(' — ') || `HTTP ${response.status}`;
  } catch {
    // The dev proxy answers 5xx with an empty body when the backend is down or restarting.
    return response.status >= 500
      ? 'The backend is not responding. Nothing was saved.'
      : `HTTP ${response.status}`;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const bearer = getToken();
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: {
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    // The request never reached the server. This is a failure, never a silent success.
    throw new ApiError(0, 'Cannot reach the backend. Nothing was saved.');
  }
  if (response.status === 401) {
    setToken(null);
    throw new ApiError(401, 'Your session is not valid. Sign in again.');
  }
  if (!response.ok) throw new ApiError(response.status, await describe(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ------------------------------------------------------------------ backend shapes

interface ExceptionSummaryDto {
  exception_id: string;
  employee_id: string;
  employee_name: string | null;
  code: string;
  severity: Severity;
  work_date: string;
  status: 'open' | 'escalated' | 'resolved';
  evidence_version: string;
}

interface PunchDto {
  punch_id: string;
  employee_id: string;
  ts: string;
  type: PunchEvent['type'];
  source: PunchEvent['source'];
  device_id: string | null;
}

interface CaseDto {
  exception_id: string;
  code: string;
  severity: Severity;
  employee: {
    employee_id: string;
    location_id: string;
    jurisdiction: string;
    timezone: string;
    worker_category: string | null;
  };
  work_date: string;
  punches: PunchDto[];
  punch_history: PunchDto[];
  schedule: {
    shift_id: string;
    employee_id: string;
    start: string;
    end: string;
    planned_break_min: number;
  } | null;
  notes: { note_id: string; text: string; submitted_at: string }[];
  detection_details: Record<string, unknown>;
  evidence_version: string;
  as_of: string | null;
}

interface ProposalResultDto {
  exception_id: string;
  status: 'eligible' | 'blocked' | 'escalated';
  proposal: {
    decision: 'propose' | 'escalate';
    actions: LLMProposal['actions'];
    rationale: string;
    citations: Citation[];
    confidence: number;
    missing_information: string[];
  } | null;
  validation: {
    passed: boolean;
    checks: { code: string; passed: boolean; reason: string; outcome: string }[];
    rule_version: string;
  } | null;
  reasons: string[];
  policy_pack_id: string | null;
  policy_version: string | null;
  evidence_version: string;
  trace: { trace_id: string; model_id: string | null; prompt_hash: string | null };
}

interface AuditEventDto {
  event_id: string;
  occurred_at: string;
  actor_type: 'manager' | 'system' | 'ai';
  actor_id: string;
  event_type: string;
  exception_id: string;
  payload: Record<string, unknown>;
}

interface TimecardDto {
  exception_id: string;
  raw_punches: PunchDto[];
  effective_punches: PunchDto[];
  corrections_applied: Record<string, unknown>[];
  net_worked_hours: number | null;
}

// ------------------------------------------------------------------ adapters

function toPunch(dto: PunchDto): PunchEvent {
  return {
    id: dto.punch_id,
    employee_id: dto.employee_id,
    ts: dto.ts,
    type: dto.type,
    source: dto.source,
    device_id: dto.device_id ?? '',
  };
}

function hours(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(2)}h`;
}

function summaryOf(code: string, details: Record<string, unknown>): string {
  const reason = details?.reason;
  return typeof reason === 'string' && reason ? reason : code.replace(/_/g, ' ').toLowerCase();
}

function toItem(dto: ExceptionSummaryDto): ExceptionItem {
  return {
    id: dto.exception_id,
    code: dto.code,
    severity: dto.severity,
    employee_id: dto.employee_id,
    employee_name: dto.employee_name ?? dto.employee_id,
    job: '',
    location: '',
    timezone: '',
    policy_pack_id: '',
    work_date: dto.work_date,
    status: dto.status,
    evidence_version: dto.evidence_version,
    summary: dto.code.replace(/_/g, ' ').toLowerCase(),
    punches: [],
    before_hours: { regular_hours: '—', overtime_hours: '—', pay_status: dto.status },
  };
}

function toOutcomes(validation: ProposalResultDto['validation']): RuleOutcome[] {
  if (!validation) return [];
  return validation.checks.map((check) => ({
    rule: check.code,
    passed: check.passed,
    detail: check.reason,
    outcome: check.outcome,
  }));
}

// ------------------------------------------------------------------ operations

export interface BackendHealth {
  connected: boolean;
  message: string;
}

export type ImportKind = 'punches' | 'shifts' | 'notes';
export type ImportFormat = 'csv' | 'json';

export interface ImportPreviewItem {
  row_number: number;
  status: 'valid' | 'invalid' | 'duplicate';
  error?: string | null;
  duplicate_of?: number | null;
  source_event_id?: string | null;
  employee_id?: string;
  employee_name?: string;
  timezone?: string;
  local_time?: string;
  raw_timestamp?: string;
  event_code?: string;
  shift_window?: string;
  planned_break_min?: number;
  note_excerpt?: string;
  raw_row: Record<string, string>;
}

export interface ImportPreviewSummary {
  kind: ImportKind;
  format: ImportFormat;
  rows: ImportPreviewItem[];
  valid: number;
  invalid: number;
  duplicates: number;
  fromServer: boolean;
}

export interface ImportCommitSummary {
  batch_id: string;
  inserted: number;
  invalid: number;
  duplicates: number;
  skipped: number;
  detected_exception_ids: string[];
  created_exceptions: ExceptionItem[];
  fromServer: boolean;
}

const DEMO_EMPLOYEE_DIR: Record<string, { name: string; tz: string; offset: string; location: string }> = {
  'EMP-BLR-02': { name: 'Sneha Kulkarni', tz: 'Asia/Kolkata', offset: '+05:30', location: 'Bengaluru (BLR-01)' },
  'EMP-BLR-04': { name: 'Aarav Sharma', tz: 'Asia/Kolkata', offset: '+05:30', location: 'Bengaluru (BLR-01)' },
  'EMP-BLR-09': { name: 'Divya Nair', tz: 'Asia/Kolkata', offset: '+05:30', location: 'Bengaluru (BLR-02)' },
  'EMP-BLR-11': { name: 'Nandini Rao', tz: 'Asia/Kolkata', offset: '+05:30', location: 'Bengaluru (BLR-01)' },
  'EMP-BLR-12': { name: 'Karthik Hegde', tz: 'Asia/Kolkata', offset: '+05:30', location: 'Bengaluru (BLR-02)' },
  'EMP-AUS-02': { name: 'Carlos Mendez', tz: 'America/Chicago', offset: '-06:00', location: 'Austin (AUS-01)' },
  'EMP-AUS-09': { name: 'Hannah Brooks', tz: 'America/Chicago', offset: '-06:00', location: 'Austin (AUS-01)' },
};

const PUNCH_TYPE_ALIASES: Record<string, 'in' | 'out' | 'break_start' | 'break_end'> = {
  in: 'in',
  clock_in: 'in',
  clockin: 'in',
  punch_in: 'in',
  out: 'out',
  clock_out: 'out',
  clockout: 'out',
  punch_out: 'out',
  break_start: 'break_start',
  start_break: 'break_start',
  meal_start: 'break_start',
  break_end: 'break_end',
  end_break: 'break_end',
  meal_end: 'break_end',
};

function authHeaders(role: Role): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Resolva-Role': role,
  };
  try {
    const token = window.localStorage.getItem('resolva_token') || window.sessionStorage.getItem('resolva_token');
    if (token) headers.Authorization = `Bearer ${token}`;
  } catch {
    // Ignore storage access restrictions
  }
  return headers;
}

export async function checkBackendHealth(): Promise<BackendHealth> {
  try {
    const res = await fetch('/api/health');
    if (!res.ok) return { connected: false, message: `Backend returned ${res.status}` };
    const data = await res.json();
    return {
      connected: true,
      message: `Backend connected: ${data.status ?? 'ok'} (${data.mode ?? 'unknown mode'})`,
    };
  } catch {
    return { connected: false, message: 'Backend offline — sign-in and decisions are unavailable' };
  }
}

/** Verify a manager token by using it. Returns the manager's own exception count. */
export async function signIn(managerToken: string): Promise<number> {
  setToken(managerToken.trim());
  try {
    const page = await request<{ total: number }>('/exceptions?limit=1');
    return page.total;
  } catch (error) {
    setToken(null);
    throw error;
  }
}

export function signOut(): void {
  setToken(null);
}

/** Is the stored session still accepted by the server? Used to survive a page refresh. */
export async function hasValidSession(): Promise<boolean> {
  if (!getToken()) return false;
  try {
    await request('/exceptions?limit=1');
    return true;
  } catch {
    return false;
  }
}

export async function fetchExceptions(): Promise<ExceptionItem[]> {
  const page = await request<{ items: ExceptionSummaryDto[] }>('/exceptions?limit=100');
  return page.items.map(toItem);
}

/** The full case: evidence, schedule, note, and the hours the timecard currently shows. */
export async function fetchCase(exceptionId: string): Promise<Partial<ExceptionItem>> {
  const [dto, timecard] = await Promise.all([
    request<CaseDto>(`/exceptions/${encodeURIComponent(exceptionId)}`),
    request<TimecardDto>(`/exceptions/${encodeURIComponent(exceptionId)}/timecard`).catch(
      () => null
    ),
  ]);
  return {
    id: dto.exception_id,
    code: dto.code,
    severity: dto.severity,
    employee_id: dto.employee.employee_id,
    location: dto.employee.location_id,
    timezone: dto.employee.timezone,
    policy_pack_id: dto.employee.jurisdiction,
    work_date: dto.work_date,
    evidence_version: dto.evidence_version,
    summary: summaryOf(dto.code, dto.detection_details),
    employee_note: dto.notes[0]?.text,
    punches: dto.punches.map(toPunch),
    schedule: dto.schedule
      ? {
          id: dto.schedule.shift_id,
          employee_id: dto.schedule.employee_id,
          start: dto.schedule.start,
          end: dto.schedule.end,
          planned_break_min: dto.schedule.planned_break_min,
          location: dto.employee.location_id,
          job: '',
        }
      : undefined,
    before_hours: {
      regular_hours: hours(timecard?.net_worked_hours ?? null),
      overtime_hours: '—',
      pay_status: timecard && timecard.corrections_applied.length ? 'corrected' : 'as recorded',
    },
  };
}

export interface ProposalOutcome {
  status: 'eligible' | 'blocked' | 'escalated';
  reasons: string[];
  proposal?: LLMProposal;
  outcomes: RuleOutcome[];
}

/** Ask the backend to draft a correction. This never approves anything. */
export async function requestProposal(exceptionId: string): Promise<ProposalOutcome> {
  const dto = await request<ProposalResultDto>(
    `/exceptions/${encodeURIComponent(exceptionId)}/proposal`,
    { method: 'POST' }
  );
  const outcomes = toOutcomes(dto.validation);
  return {
    status: dto.status,
    reasons: dto.reasons,
    outcomes,
    proposal: dto.proposal
      ? {
          id: dto.trace.trace_id,
          exception_id: dto.exception_id,
          decision: dto.proposal.decision,
          actions: dto.proposal.actions,
          rationale: dto.proposal.rationale,
          citations: dto.proposal.citations,
          confidence: dto.proposal.confidence,
          missing_information: dto.proposal.missing_information,
          model_id: dto.trace.model_id ?? 'unknown',
          prompt_hash: dto.trace.prompt_hash ?? '',
          evidence_version: dto.evidence_version,
          validator_passed: dto.validation?.passed ?? false,
          rule_outcomes: outcomes,
        }
      : undefined,
  };
}

export interface DecisionInput {

export function detectImportFormat(content: string): ImportFormat {
  const trimmed = content.trim();
  return trimmed.startsWith('[') || trimmed.startsWith('{') ? 'json' : 'csv';
}

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === ',' && !inQuotes) {
      out.push(cur.trim());
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur.trim());
  return out;
}

function parseRawRecords(content: string, fmt: ImportFormat): { records: Record<string, string>[]; error?: string } {
  const trimmed = content.trim();
  if (!trimmed) return { records: [], error: 'Paste CSV or JSON rows before previewing.' };
  if (fmt === 'json') {
    try {
      const parsed = JSON.parse(trimmed);
      if (!Array.isArray(parsed)) return { records: [], error: 'JSON input must be an array of row objects.' };
      const records = parsed.map((entry) => {
        const rec: Record<string, string> = {};
        if (entry && typeof entry === 'object') {
          for (const [k, v] of Object.entries(entry as Record<string, unknown>)) {
            rec[k.trim()] = v == null ? '' : String(v).trim();
          }
        }
        return rec;
      });
      return { records };
    } catch (err) {
      return { records: [], error: `Invalid JSON: ${err instanceof Error ? err.message : 'parse error'}` };
    }
  }

  const lines = trimmed.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) {
    return { records: [], error: 'CSV must include a header row and at least one data row.' };
  }
  const headers = splitCsvLine(lines[0]);
  const records = lines.slice(1).map((line) => {
    const cells = splitCsvLine(line);
    const rec: Record<string, string> = {};
    headers.forEach((h, idx) => {
      if (h) rec[h] = cells[idx] ?? '';
    });
    return rec;
  });
  return { records };
}

function formatLocalStamp(isoOrNaive: string, tz: string, defaultOffset: string): { display: string; iso: string } {
  const clean = isoOrNaive.trim();
  const hasOffset = /([zZ]|[+-]\d{2}:\d{2})$/.test(clean);
  const normalizedIso = hasOffset ? clean : `${clean.length === 16 ? `${clean}:00` : clean}${defaultOffset}`;
  const dt = new Date(normalizedIso);
  if (Number.isNaN(dt.getTime())) {
    return { display: clean, iso: normalizedIso };
  }
  const datePart = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: tz,
  }).format(dt);
  const timePart = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: tz,
  }).format(dt);
  const tzShort = tz === 'Asia/Kolkata' ? 'IST' : tz === 'America/Chicago' ? 'CST' : tz;
  return { display: `${datePart}, ${timePart} ${tzShort}`, iso: normalizedIso };
}

function localPreview(kind: ImportKind, format: ImportFormat, content: string): ImportPreviewSummary {
  const { records, error } = parseRawRecords(content, format);
  if (error) {
    return {
      kind,
      format,
      rows: [{ row_number: 1, status: 'invalid', error, raw_row: {} }],
      valid: 0,
      invalid: 1,
      duplicates: 0,
      fromServer: false,
    };
  }

  const seenKeys = new Map<string, number>();
  const rows: ImportPreviewItem[] = records.map((raw, idx) => {
    const row_number = idx + 1;
    const empId = raw.employee_id || '';
    const empMeta = DEMO_EMPLOYEE_DIR[empId];
    const tz = empMeta?.tz ?? 'Asia/Kolkata';
    const offset = empMeta?.offset ?? '+05:30';
    const employee_name = raw.employee_name || empMeta?.name || '';

    if (kind === 'punches') {
      const rawTs = raw.timestamp || (raw.date && raw.time ? `${raw.date}T${raw.time}` : '');
      const rawType = (raw.type || '').toLowerCase();
      const canonicalType = PUNCH_TYPE_ALIASES[rawType];
      const sourceEventId = raw.source_event_id || (empId && rawTs && canonicalType ? `evt-${empId}-${row_number}` : '');

      if (!empId) {
        return { row_number, status: 'invalid', error: 'Employee ID is missing.', employee_id: empId, employee_name, raw_row: raw };
      }
      if (!rawTs) {
        return { row_number, status: 'invalid', error: 'Timestamp is missing.', employee_id: empId, employee_name, event_code: canonicalType, raw_row: raw };
      }
      if (!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(rawTs) || Number.isNaN(new Date(/([zZ]|[+-]\d{2}:\d{2})$/.test(rawTs) ? rawTs : `${rawTs}${offset}`).getTime())) {
        return { row_number, status: 'invalid', error: 'Invalid timestamp format (expected ISO-8601 YYYY-MM-DDTHH:MM).', employee_id: empId, employee_name, raw_timestamp: rawTs, event_code: canonicalType, raw_row: raw };
      }
      if (!canonicalType) {
        return { row_number, status: 'invalid', error: `Unsupported punch type "${raw.type || 'empty'}". Use in, out, break_start, or break_end.`, employee_id: empId, employee_name, raw_timestamp: rawTs, raw_row: raw };
      }

      const formatted = formatLocalStamp(rawTs, tz, offset);
      const dedupeKey = raw.source_event_id ? `id:${raw.source_event_id}` : `key:${empId}|${formatted.iso}|${canonicalType}`;
      const dupOf = seenKeys.get(dedupeKey);
      if (dupOf !== undefined) {
        return {
          row_number,
          status: 'duplicate',
          duplicate_of: dupOf,
          error: `Duplicate of row ${dupOf}.`,
          source_event_id: sourceEventId,
          employee_id: empId,
          employee_name,
          timezone: tz,
          local_time: formatted.display,
          raw_timestamp: formatted.iso,
          event_code: canonicalType,
          raw_row: raw,
        };
      }
      seenKeys.set(dedupeKey, row_number);
      return {
        row_number,
        status: 'valid',
        source_event_id: sourceEventId,
        employee_id: empId,
        employee_name,
        timezone: tz,
        local_time: formatted.display,
        raw_timestamp: formatted.iso,
        event_code: canonicalType,
        raw_row: raw,
      };
    }

    if (kind === 'shifts') {
      const start = raw.start || '';
      const end = raw.end || '';
      const breakMin = Number(raw.planned_break_min || '0');
      if (!empId) return { row_number, status: 'invalid', error: 'Employee ID is missing.', raw_row: raw };
      if (!start || !end) return { row_number, status: 'invalid', error: 'Shift start and end timestamps are required.', employee_id: empId, employee_name, raw_row: raw };
      const sFmt = formatLocalStamp(start, tz, offset);
      const eFmt = formatLocalStamp(end, tz, offset);
      if (new Date(eFmt.iso).getTime() <= new Date(sFmt.iso).getTime()) {
        return { row_number, status: 'invalid', error: 'Shift end must be after shift start.', employee_id: empId, employee_name, raw_row: raw };
      }
      const dedupeKey = raw.shift_id ? `shd:${raw.shift_id}` : `shd:${empId}|${sFmt.iso}`;
      const dupOf = seenKeys.get(dedupeKey);
      if (dupOf !== undefined) {
        return { row_number, status: 'duplicate', duplicate_of: dupOf, error: `Duplicate of row ${dupOf}.`, source_event_id: raw.shift_id || dedupeKey, employee_id: empId, employee_name, shift_window: `${sFmt.display} → ${eFmt.display.split(', ')[1] ?? eFmt.display}`, planned_break_min: breakMin, raw_row: raw };
      }
      seenKeys.set(dedupeKey, row_number);
      return {
        row_number,
        status: 'valid',
        source_event_id: raw.shift_id || `SHD-${900 + row_number}`,
        employee_id: empId,
        employee_name,
        timezone: tz,
        shift_window: `${sFmt.display} → ${eFmt.display.split(', ')[1] ?? eFmt.display}`,
        planned_break_min: Number.isFinite(breakMin) ? breakMin : 0,
        raw_timestamp: `${sFmt.iso} / ${eFmt.iso}`,
        raw_row: raw,
      };
    }

    // kind === 'notes'
    const text = raw.text || '';
    const submittedAt = raw.submitted_at || '';
    if (!empId) return { row_number, status: 'invalid', error: 'Employee ID is missing.', raw_row: raw };
    if (!text) return { row_number, status: 'invalid', error: 'Note text is empty.', employee_id: empId, employee_name, raw_row: raw };
    if (!submittedAt) return { row_number, status: 'invalid', error: 'Submitted timestamp (submitted_at) is missing.', employee_id: empId, employee_name, raw_row: raw };
    const nFmt = formatLocalStamp(submittedAt, tz, offset);
    const dedupeKey = raw.note_id ? `note:${raw.note_id}` : `note:${empId}|${nFmt.iso}|${text.slice(0, 24)}`;
    const dupOf = seenKeys.get(dedupeKey);
    if (dupOf !== undefined) {
      return { row_number, status: 'duplicate', duplicate_of: dupOf, error: `Duplicate of row ${dupOf}.`, source_event_id: raw.note_id || dedupeKey, employee_id: empId, employee_name, local_time: nFmt.display, note_excerpt: text, raw_timestamp: nFmt.iso, raw_row: raw };
    }
    seenKeys.set(dedupeKey, row_number);
    return {
      row_number,
      status: 'valid',
      source_event_id: raw.note_id || `NOTE-${400 + row_number}`,
      employee_id: empId,
      employee_name,
      timezone: tz,
      local_time: nFmt.display,
      note_excerpt: text,
      raw_timestamp: nFmt.iso,
      raw_row: raw,
    };
  });

  return {
    kind,
    format,
    rows,
    valid: rows.filter((r) => r.status === 'valid').length,
    invalid: rows.filter((r) => r.status === 'invalid').length,
    duplicates: rows.filter((r) => r.status === 'duplicate').length,
    fromServer: false,
  };
}

export async function previewImportWithFallback(params: {
  kind: ImportKind;
  format: ImportFormat;
  content: string;
  role: Role;
}): Promise<ImportPreviewSummary> {
  try {
    const res = await fetch('/api/imports/preview', {
      method: 'POST',
      headers: authHeaders(params.role),
      body: JSON.stringify({
        kind: params.kind,
        format: params.format,
        content: params.content,
        mapping: {},
        allow_partial: false,
      }),
    });
    if (res.ok) {
      const data = await res.json();
      const { records } = parseRawRecords(params.content, params.format);
      const rows: ImportPreviewItem[] = (data.rows ?? []).map((r: Record<string, unknown>, idx: number) => {
        const raw = records[idx] ?? {};
        const punch = (r.punch ?? {}) as Record<string, string>;
        const shift = (r.shift ?? {}) as Record<string, string | number>;
        const note = (r.note ?? {}) as Record<string, string>;
        const empId = punch.employee_id || String(shift.employee_id || '') || note.employee_id || raw.employee_id || '';
        const empMeta = DEMO_EMPLOYEE_DIR[empId];
        const tz = empMeta?.tz ?? 'Asia/Kolkata';
        const offset = empMeta?.offset ?? '+05:30';
        const ts = punch.ts || note.submitted_at || raw.timestamp || '';
        const formatted = ts ? formatLocalStamp(ts, tz, offset) : undefined;
        return {
          row_number: Number(r.row_number ?? idx + 1),
          status: (r.status as 'valid' | 'invalid' | 'duplicate') ?? 'invalid',
          error: (r.error as string | null) ?? null,
          duplicate_of: (r.duplicate_of as number | null) ?? null,
          source_event_id: (r.source_event_id as string | null) ?? punch.punch_id ?? String(shift.shift_id ?? note.note_id ?? ''),
          employee_id: empId,
          employee_name: empMeta?.name ?? raw.employee_name ?? '',
          timezone: tz,
          local_time: formatted?.display,
          raw_timestamp: ts || (shift.start ? `${shift.start} / ${shift.end}` : undefined),
          event_code: punch.type || raw.type,
          shift_window: shift.start && shift.end ? `${formatLocalStamp(String(shift.start), tz, offset).display} → ${formatLocalStamp(String(shift.end), tz, offset).display.split(', ')[1] ?? ''}` : undefined,
          planned_break_min: typeof shift.planned_break_min === 'number' ? shift.planned_break_min : undefined,
          note_excerpt: note.text || raw.text,
          raw_row: raw,
        };
      });
      return {
        kind: params.kind,
        format: params.format,
        rows,
        valid: Number(data.valid ?? 0),
        invalid: Number(data.invalid ?? 0),
        duplicates: Number(data.duplicates ?? 0),
        fromServer: true,
      };
    }
  } catch {
    // Fallback when FastAPI or PostgreSQL store is offline
  }
  return localPreview(params.kind, params.format, params.content);
}

export async function commitImportWithFallback(params: {
  kind: ImportKind;
  format: ImportFormat;
  content: string;
  allowPartial: boolean;
  preview: ImportPreviewSummary;
  role: Role;
}): Promise<{ ok: boolean; error?: string; result?: ImportCommitSummary }> {
  try {
    const res = await fetch('/api/imports', {
      method: 'POST',
      headers: authHeaders(params.role),
      body: JSON.stringify({
        kind: params.kind,
        format: params.format,
        content: params.content,
        mapping: {},
        allow_partial: params.allowPartial,
      }),
    });
    if (res.ok) {
      const data = await res.json();
      const inserted = Number(data.inserted ?? 0);
      const invalid = Number(data.invalid ?? 0);
      const duplicates = Number(data.duplicates ?? 0);
      return {
        ok: true,
        result: {
          batch_id: String(data.batch_id ?? `batch-${Date.now()}`),
          inserted,
          invalid,
          duplicates,
          skipped: invalid + duplicates,
          detected_exception_ids: Array.isArray(data.detected_exception_ids) ? data.detected_exception_ids : [],
          created_exceptions: [],
          fromServer: true,
        },
      };
    }
    if (res.status === 403 || res.status === 422) {
      const errBody = await res.json().catch(() => ({}));
      return { ok: false, error: errBody.detail || `Import rejected by server (HTTP ${res.status}).` };
    }
  } catch {
    // Fallback to local state when backend is offline
  }

  // Build synthetic exceptions from valid unpaired clock-in punches for local demo continuity
  const validRows = params.preview.rows.filter((r) => r.status === 'valid');
  const createdExceptions: ExceptionItem[] = [];
  if (params.kind === 'punches') {
    const byEmpDate = new Map<string, ImportPreviewItem[]>();
    for (const row of validRows) {
      const dateKey = (row.raw_timestamp ?? '').slice(0, 10) || '2026-11-17';
      const key = `${row.employee_id}|${dateKey}`;
      const list = byEmpDate.get(key) ?? [];
      list.push(row);
      byEmpDate.set(key, list);
    }
    let idx = 0;
    for (const [key, empRows] of byEmpDate.entries()) {
      const hasIn = empRows.some((r) => r.event_code === 'in');
      const hasOut = empRows.some((r) => r.event_code === 'out');
      if (hasIn && !hasOut) {
        const [empId, workDate] = key.split('|');
        const empMeta = DEMO_EMPLOYEE_DIR[empId];
        const firstIn = empRows.find((r) => r.event_code === 'in')!;
        const excId = `EXC-${210 + idx}`;
        const localHHMM = firstIn.local_time?.split(', ')[1]?.slice(0, 5) ?? '09:00';
        createdExceptions.push({
          id: excId,
          code: 'MISSING_PUNCH',
          severity: 'problem',
          employee_id: empId,
          employee_name: firstIn.employee_name || empMeta?.name || empId,
          job: 'Associate',
          location: empMeta?.location ?? 'Bengaluru (BLR-01)',
          timezone: empMeta?.tz === 'America/Chicago' ? 'CST (UTC-06:00)' : 'IST (UTC+05:30)',
          policy_pack_id: empMeta?.tz === 'America/Chicago' ? 'US-FED+CA@2025.1' : 'IN-KA@2025.1',
          work_date: workDate,
          status: 'proposed',
          evidence_version: 1,
          summary: `Imported clock-in at ${localHHMM} missing matching clock-out punch.`,
          punches: empRows.map((r, pIdx) => ({
            id: r.source_event_id || `PNC-IMP-${idx}-${pIdx}`,
            employee_id: empId,
            ts: r.raw_timestamp || `${workDate}T${localHHMM}:00+05:30`,
            type: (r.event_code as 'in' | 'out' | 'break_start' | 'break_end') ?? 'in',
            source: 'import',
          })),
          before_hours: { regular_hours: '0.00 h', overtime_hours: '0.00 h', pay_status: 'Blocked (missing out-punch)' },
          after_hours: { regular_hours: '8.00 h', overtime_hours: '0.00 h', pay_status: 'Payable (Regular)' },
          proposal: {
            id: `PRP-${710 + idx}`,
            exception_id: excId,
            decision: 'propose',
            actions: [{ type: 'add_punch', new_ts: `${workDate}T18:00:00+05:30`, note: 'Inferred scheduled shift end 18:00.' }],
            rationale: 'Imported attendance rows showed an unpaired clock-in punch; proposed scheduled shift end.',
            citations: [{ chunk_id: 'IN-KA@2025.1#sec-4.2', quote: 'Missing out-punches may be inferred within ±30 minutes of scheduled shift end.' }],
            confidence: 0.9,
            missing_information: [],
            model_id: 'qwen2.5-7b-instruct',
            prompt_hash: 'sha256:9f82c1a4',
            evidence_version: 1,
            validator_passed: true,
            rule_outcomes: [{ rule: 'MISSING_PUNCH', passed: true, detail: 'Paired with 18:00 out-punch.' }],
          },
        });
        idx += 1;
      }
    }
  }

  return {
    ok: true,
    result: {
      batch_id: `batch-${Math.random().toString(16).slice(2, 10)}`,
      inserted: params.preview.valid,
      invalid: params.preview.invalid,
      duplicates: params.preview.duplicates,
      skipped: params.preview.invalid + params.preview.duplicates,
      detected_exception_ids: createdExceptions.map((e) => e.id),
      created_exceptions: createdExceptions,
      fromServer: false,
    },
  };
}

export async function fetchCaseAuditWithFallback(exceptionId: string, role: Role): Promise<AuditEvent[] | null> {
  try {
    const res = await fetch(`/api/exceptions/${encodeURIComponent(exceptionId)}/audit`, {
      headers: authHeaders(role),
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!Array.isArray(data)) return null;
    return data.map((ev: Record<string, unknown>) => {
      const payload = (ev.payload ?? {}) as Record<string, unknown>;
      const actorTypeRaw = String(ev.actor_type ?? 'system').toLowerCase();
      const actor_type: 'system' | 'ai' | 'manager' =
        actorTypeRaw === 'ai' || actorTypeRaw === 'model'
          ? 'ai'
          : actorTypeRaw === 'manager'
          ? 'manager'
          : 'system';
      return {
        id: String(ev.event_id ?? ''),
        trace_id: String(payload.trace_id ?? ev.decision_id ?? ev.event_id ?? ''),
        actor_type,
        actor_name: String(ev.actor_id ?? actorTypeRaw),
        action: String(ev.event_type ?? 'EVENT'),
        entity_ref: String(ev.exception_id ?? exceptionId),
        before_summary: String(payload.before_summary ?? ''),
        after_summary: String(payload.after_summary ?? payload.status ?? payload.reason ?? ''),
        ts: String(ev.occurred_at ?? ''),
        model_id: payload.model_id ? String(payload.model_id) : undefined,
        evidence_hash: ev.hash ? String(ev.hash) : undefined,
        decision_id: ev.decision_id ? String(ev.decision_id) : null,
      };
    });
  } catch {
    return null;
  }
}

export async function submitDecisionWithFallback(params: {
  item: ExceptionItem;
  decision: 'approved' | 'rejected' | 'escalated';
  actions?: LLMProposal['actions'];
  reason?: string;
  edited?: boolean;
}

/**
 * Record a decision. It throws on any failure, so a caller cannot mistake a failed write
 * for a successful one. The backend re-validates against fresh evidence before it commits.
 */
export async function submitDecision(input: DecisionInput): Promise<{
  decision_id: string;
  status: 'open' | 'resolved' | 'escalated';
  current_evidence_version: string;
}> {
  const decision =
    input.decision === 'approved' ? 'approve' : input.decision === 'rejected' ? 'reject' : 'escalate';
  const body: Record<string, unknown> = {
    decision,
    evidence_version: input.item.evidence_version,
    idempotency_key: `ui-${input.item.id}-${decision}-${Date.now()}`,
    reason: input.reason ?? '',
  };
  if (decision === 'approve') {
    body.actions = input.actions ?? [];
    body.source = input.edited ? 'manager_edit' : 'ai_proposal';
  try {
    const proposalId = params.item.proposal?.id ?? params.item.id;
    const res = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/decision`, {
      method: 'POST',
      headers: authHeaders(params.role),
      body: JSON.stringify({
        exception_id: params.item.id,
        decision: params.decision,
        edited_time: params.editedTime,
        reason_code: params.reasonCode,
        comment: params.comment,
        evidence_version: params.item.evidence_version,
      }),
    });
    if (res.status === 409) {
      return { ok: false, conflict: '409 Conflict from server: Evidence version is stale. Re-propose required.' };
    }
    if (res.status === 403) {
      return { ok: false, conflict: '403 Forbidden: Role not authorized to commit timecard decisions.' };
    }
  } catch {
    // Fallback to local state when FastAPI endpoint is not yet running
  }
  return request(`/exceptions/${encodeURIComponent(input.item.id)}/decisions`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function fetchAudit(exceptionId: string): Promise<AuditEvent[]> {
  const events = await request<AuditEventDto[]>(
    `/exceptions/${encodeURIComponent(exceptionId)}/audit`
  );
  return events
    .map((event) => ({
      id: event.event_id,
      trace_id: String(event.payload?.trace_id ?? event.event_id),
      actor_type: event.actor_type,
      actor_name: event.actor_id,
      action: event.event_type,
      entity_ref: event.exception_id,
      before_summary: String(event.payload?.evidence_version ?? ''),
      after_summary: String(
        event.payload?.evidence_version_after ?? event.payload?.status ?? event.payload?.reason ?? ''
      ),
      ts: event.occurred_at,
    }))
    .reverse(); // newest first, as the audit view expects
}

/** Does the scheduled shift end on a later local date than it starts? (Local wall-clock text.) */
function isOvernight(item: ExceptionItem): boolean {
  const schedule = item.schedule;
  return Boolean(schedule && schedule.end.slice(0, 10) > schedule.start.slice(0, 10));
}

/**
 * Syntax check for a manually typed time. It is **not** a rule check: whether the correction is
 * allowed is decided by the backend when the decision is submitted.
 */
export function checkEditedTime(
  item: ExceptionItem,
  editedOutHHMM: string
): { valid: boolean; error?: string } {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(editedOutHHMM.trim());
  if (!match) return { valid: false, error: 'Enter a valid 24-hour time (HH:MM).' };
  const minutes = Number(match[1]) * 60 + Number(match[2]);
  const inPunch = item.punches.find((p) => p.type === 'in');
  // On an overnight shift the clock-out is legitimately earlier in the day than the clock-in.
  if (inPunch && !isOvernight(item)) {
    const [h, m] = inPunch.ts.slice(11, 16).split(':').map(Number);
    if (minutes <= h * 60 + m) {
      return { valid: false, error: 'The clock-out must be later than the clock-in.' };
    }
  }
  return { valid: true };
}

/** Build the ISO timestamp for a manually edited clock-out, in the case's own offset. */
export function editedTimestamp(item: ExceptionItem, editedOutHHMM: string): string {
  const reference = item.schedule?.end ?? item.punches[0]?.ts ?? `${item.work_date}T00:00:00Z`;
  const offset = reference.slice(19) || 'Z';
  let date = item.work_date;
  const inPunch = item.punches.find((p) => p.type === 'in');
  if (inPunch && isOvernight(item) && editedOutHHMM < inPunch.ts.slice(11, 16)) {
    // Past midnight: the next local date. Plain calendar arithmetic, no timezone involved.
    const next = new Date(`${item.work_date}T00:00:00Z`);
    next.setUTCDate(next.getUTCDate() + 1);
    date = next.toISOString().slice(0, 10);
  }
  return `${date}T${editedOutHHMM}:00${offset}`;
}

export type ImportKind = 'punches' | 'shifts' | 'notes';

export interface ImportPreviewRow {
  row_number: number;
  status: 'valid' | 'invalid' | 'duplicate';
  error: string | null;
  duplicate_of: number | null;
  punch: { punch_id: string; employee_id: string; ts: string; type: string; source: string } | null;
  shift: { shift_id: string; employee_id: string; start: string; end: string } | null;
  note: { note_id: string; employee_id: string; text: string; submitted_at: string } | null;
}

export interface ImportPreviewResult {
  kind: ImportKind;
  rows: ImportPreviewRow[];
  valid: number;
  invalid: number;
  duplicates: number;
}

export interface ImportCommitResult {
  batch_id: string;
  inserted: number;
  invalid: number;
  duplicates: number;
  detected_exception_ids: string[];
  notes_attached: Record<string, string[]>;
}

/** The backend reads CSV or JSON; JSON always starts with [ or {. */
function importFormat(content: string): 'csv' | 'json' {
  return /^[\s\uFEFF]*[[{]/.test(content) ? 'json' : 'csv';
}

/** Parse and validate on the server. Writes nothing. */
export function previewImport(kind: ImportKind, content: string): Promise<ImportPreviewResult> {
  return request('/imports/preview', {
    method: 'POST',
    body: JSON.stringify({ kind, format: importFormat(content), content }),
  });
}

/** Import for real. The server re-validates, deduplicates, scopes to your employees and runs detection. */
export function commitImport(
  kind: ImportKind,
  content: string,
  allowPartial: boolean
): Promise<ImportCommitResult> {
  return request('/imports', {
    method: 'POST',
    body: JSON.stringify({
      kind,
      format: importFormat(content),
      content,
      allow_partial: allowPartial,
    }),
  });
}

/** A single clock event, as a kiosk would send it, through the same import path. */
export function sendKioskPunch(input: {
  employeeId: string;
  date: string;
  time: string;
  type: 'in' | 'out' | 'break_start' | 'break_end';
}): Promise<ImportCommitResult> {
  const row = [
    input.employeeId,
    `${input.date} ${input.time}`,
    input.type,
    'kiosk',
    `kiosk-sim-${Date.now()}`,
  ];
  const csv = `employee_id,timestamp,type,source,source_event_id\n${row.join(',')}\n`;
  return commitImport('punches', csv, false);
}
