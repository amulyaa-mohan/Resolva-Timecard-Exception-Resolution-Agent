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
  ImportRow,
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
  if (inPunch) {
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
  return `${item.work_date}T${editedOutHHMM}:00${offset}`;
}

/** Client-side preview of an attendance CSV before the backend import endpoint sees it. */
export function parseAndValidateImportCsv(csvText: string): ImportRow[] {
  const lines = csvText
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length <= 1) return [];
  return lines.slice(1).map((line, idx) => {
    const [employee_id = '', employee_name = '', work_date = '', in_time = '', out_time = '', location = ''] =
      line.split(',').map((c) => c.trim());
    const row_num = idx + 2;
    const base = { row_num, employee_id, employee_name, work_date, in_time, out_time, location };
    if (!employee_id) return { ...base, valid: false, error: 'Missing employee_id.' };
    if (!/^\d{4}-\d{2}-\d{2}$/.test(work_date)) {
      return { ...base, valid: false, error: 'Invalid work_date (expected YYYY-MM-DD).' };
    }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(in_time)) {
      return { ...base, valid: false, error: 'Invalid in_time (expected HH:MM).' };
    }
    if (out_time && !/^([01]\d|2[0-3]):[0-5]\d$/.test(out_time)) {
      return { ...base, valid: false, error: 'Invalid out_time (expected HH:MM or blank).' };
    }
    return { ...base, valid: true };
  });
}
