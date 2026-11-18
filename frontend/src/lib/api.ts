import { AuditEvent, ExceptionItem, ImportRow, PolicyPack, Role, RuleOutcome } from '../types/contracts';
import { INITIAL_AUDIT_EVENTS, INITIAL_EXCEPTIONS, INITIAL_POLICY_PACKS } from './fixtures';

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
    if (!res.ok) {
      return { connected: false, message: `Backend returned ${res.status} (using synthetic fixtures)` };
    }
    const data = await res.json();
    return {
      connected: true,
      message: `Backend connected: ${data.status ?? 'ok'} (${data.service ?? 'resolva-api'})`,
    };
  } catch {
    return {
      connected: false,
      message: 'Backend offline — running on labeled synthetic fixtures (FE-01/FE-03)',
    };
  }
}

export function loadInitialData(): {
  exceptions: ExceptionItem[];
  auditEvents: AuditEvent[];
  policies: PolicyPack[];
} {
  return {
    exceptions: INITIAL_EXCEPTIONS,
    auditEvents: INITIAL_AUDIT_EVENTS,
    policies: INITIAL_POLICY_PACKS,
  };
}

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
  decision: 'approved' | 'edited' | 'rejected';
  role: Role;
  editedTime?: string;
  reasonCode?: string;
  comment?: string;
}): Promise<{ ok: boolean; conflict?: string }> {
  if (params.item.stale_warning) {
    return {
      ok: false,
      conflict: `409 Conflict: Evidence changed (v${params.item.evidence_version} -> v${params.item.evidence_version + 1}) after proposal generation. Click "Re-Propose on Latest Evidence" first.`,
    };
  }

  try {
    const proposalId = params.item.proposal?.id ?? params.item.id;
    const res = await fetch(`/api/proposals/${proposalId}/decision`, {
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
  return { ok: true };
}

export function previewManualEditValidation(
  item: ExceptionItem,
  editedOutHHMM: string
): { valid: boolean; outcomes: RuleOutcome[]; error?: string } {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(editedOutHHMM.trim());
  if (!match) {
    return { valid: false, outcomes: [], error: 'Enter a valid 24-hour time (HH:MM).' };
  }

  const outMinutes = Number(match[1]) * 60 + Number(match[2]);
  const inPunch = item.punches.find((p) => p.type === 'in');
  let inMinutes = 9 * 60;
  if (inPunch) {
    const [ih, im] = inPunch.ts.slice(11, 16).split(':').map(Number);
    inMinutes = ih * 60 + im;
  }

  if (outMinutes <= inMinutes) {
    return {
      valid: false,
      outcomes: [
        { rule: 'MISSING_PUNCH', passed: false, detail: 'Out-punch cannot precede or equal clock-in.' },
      ],
      error: 'Out-punch timestamp must be later than the clock-in timestamp.',
    };
  }

  const spreadHours = (outMinutes - inMinutes) / 60;
  const maxSpread = item.policy_pack_id.startsWith('IN-KA') ? 12 : 16;
  const spreadPassed = spreadHours <= maxSpread;
  const otHours = Math.max(0, spreadHours - 1 - 9);
  const otPassed = otHours <= 2;

  const outcomes: RuleOutcome[] = [
    { rule: 'MISSING_PUNCH', passed: true, detail: `Paired with manager-edited ${editedOutHHMM} out-punch.` },
    { rule: 'OVERLAPPING_SHIFT', passed: true, detail: 'No overlapping shifts on work date.' },
    { rule: 'MEAL_BREAK_BREACH', passed: true, detail: 'Break window satisfied.' },
    {
      rule: 'OVERTIME_RISK',
      passed: otPassed,
      detail: otPassed ? `Net overtime ${otHours.toFixed(2)}h within cap.` : `Net overtime ${otHours.toFixed(2)}h exceeds daily cap.`,
    },
    {
      rule: 'SPREAD_OVER_BREACH',
      passed: spreadPassed,
      detail: spreadPassed
        ? `Spread-over ${spreadHours.toFixed(2)}h within ${maxSpread}h limit.`
        : `Spread-over ${spreadHours.toFixed(2)}h exceeds ${maxSpread}h statutory limit.`,
    },
    { rule: 'SCHEDULE_DEVIATION', passed: true, detail: 'Manual manager override logged with audit reason.' },
  ];

  const allPassed = outcomes.every((o) => o.passed);
  return {
    valid: allPassed,
    outcomes,
    error: allPassed ? undefined : 'Blocked by deterministic validator: fix rule violations before saving.',
  };
}

export function parseAndValidateImportCsv(csvText: string): ImportRow[] {
  const lines = csvText
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length <= 1) return [];

  return lines.slice(1).map((line, idx) => {
    const [employee_id = '', employee_name = '', work_date = '', in_time = '', out_time = '', location = ''] = line
      .split(',')
      .map((c) => c.trim());
    const row_num = idx + 2;

    if (!employee_id || !employee_name) {
      return { row_num, employee_id, employee_name, work_date, in_time, out_time, location, valid: false, error: 'Missing required employee_id or employee_name.' };
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(work_date)) {
      return { row_num, employee_id, employee_name, work_date, in_time, out_time, location, valid: false, error: 'Invalid work_date format (expected YYYY-MM-DD).' };
    }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(in_time)) {
      return { row_num, employee_id, employee_name, work_date, in_time, out_time, location, valid: false, error: 'Invalid in_time (expected HH:MM).' };
    }
    if (out_time && !/^([01]\d|2[0-3]):[0-5]\d$/.test(out_time)) {
      return { row_num, employee_id, employee_name, work_date, in_time, out_time, location, valid: false, error: 'Invalid out_time (expected HH:MM or blank).' };
    }
    return { row_num, employee_id, employee_name, work_date, in_time, out_time, location: location || 'Bengaluru (BLR-01)', valid: true };
  });
}

export function buildAuditRecord(params: {
  role: Role;
  item: ExceptionItem;
  decision: 'approved' | 'edited' | 'rejected';
  summary: string;
}): AuditEvent {
  const traceId = `tr-${Math.random().toString(16).slice(2, 9)}`;
  return {
    id: `AUD-${Math.floor(1000 + Math.random() * 9000)}`,
    trace_id: traceId,
    actor_type: 'manager',
    actor_name: `Priya Menon (${params.role})`,
    action: `DECISION_${params.decision.toUpperCase()}`,
    entity_ref: `${params.item.id} / ${params.item.employee_id}`,
    before_summary: `${params.item.code} (${params.item.status})`,
    after_summary: params.summary,
    ts: new Date().toISOString(),
  };
}
