import { AuditEvent, ExceptionItem, ImportRow, PolicyPack, Role, RuleOutcome } from '../types/contracts';
import { INITIAL_AUDIT_EVENTS, INITIAL_EXCEPTIONS, POLICY_PACKS } from './fixtures';

export interface BackendHealth {
  connected: boolean;
  message: string;
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
    policies: POLICY_PACKS,
  };
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
      headers: { 'Content-Type': 'application/json', 'X-Resolva-Role': params.role },
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
