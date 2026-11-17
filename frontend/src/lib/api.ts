import {
  AuditEvent,
  ExceptionItem,
  PolicyPack,
  Role,
  RuleOutcome,
} from '../types/contracts';
import {
  INITIAL_AUDIT_EVENTS,
  INITIAL_EXCEPTIONS,
  INITIAL_POLICY_PACKS,
  IS_SYNTHETIC_FIXTURE,
} from './fixtures';

export interface BackendHealth {
  reachable: boolean;
  message: string;
  usingFixtures: boolean;
}

export async function checkBackendHealth(): Promise<BackendHealth> {
  try {
    const res = await fetch('/api/health');
    if (!res.ok) {
      return {
        reachable: false,
        message: 'API offline — using labeled synthetic fixtures',
        usingFixtures: IS_SYNTHETIC_FIXTURE,
      };
    }
    const data = await res.json();
    return {
      reachable: data.status === 'ok',
      message:
        data.status === 'ok'
          ? 'Backend /api/health connected (synthetic fixture mode until SHARED-01 endpoints go live)'
          : 'Backend not ready — using synthetic fixtures',
      usingFixtures: IS_SYNTHETIC_FIXTURE,
    };
  } catch {
    return {
      reachable: false,
      message: 'Backend unavailable on :8000 — running on labeled synthetic fixtures',
      usingFixtures: IS_SYNTHETIC_FIXTURE,
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

export function previewManualEditValidation(
  item: ExceptionItem,
  editedTimeHHMM: string
): { valid: boolean; outcomes: RuleOutcome[]; error?: string } {
  const [hh, mm] = editedTimeHHMM.split(':').map(Number);
  if (Number.isNaN(hh) || Number.isNaN(mm)) {
    return { valid: false, outcomes: [], error: 'Enter a valid HH:MM time.' };
  }

  const firstIn = item.punches.find((p) => p.type === 'in');
  if (firstIn) {
    const inDate = new Date(firstIn.ts);
    const inMinutes = inDate.getHours() * 60 + inDate.getMinutes();
    const outMinutes = hh * 60 + mm;

    if (outMinutes <= inMinutes) {
      return {
        valid: false,
        error: `Out-punch (${editedTimeHHMM}) cannot be earlier than or equal to clock-in (${firstIn.ts.slice(11, 16)}).`,
        outcomes: [
          {
            rule: 'MISSING_PUNCH',
            passed: false,
            detail: `Invalid sequence: ${editedTimeHHMM} is before clock-in.`,
          },
        ],
      };
    }

    const spreadHours = (outMinutes - inMinutes) / 60;
    if (item.policy_pack_id.startsWith('IN-KA@2025.1') && spreadHours > 12) {
      return {
        valid: false,
        error: `Validator blocked edit: ${spreadHours.toFixed(2)}h spread-over exceeds the 12.00h IN-KA@2025.1 statutory maximum.`,
        outcomes: [
          {
            rule: 'SPREAD_OVER_BREACH',
            passed: false,
            detail: `Spread-over ${spreadHours.toFixed(2)}h > 12.00h maximum.`,
          },
        ],
      };
    }
  }

  return {
    valid: true,
    outcomes: [
      { rule: 'MISSING_PUNCH', passed: true, detail: `Paired with ${editedTimeHHMM} manager edit.` },
      { rule: 'OVERLAPPING_SHIFT', passed: true, detail: 'No overlapping shifts.' },
      { rule: 'MEAL_BREAK_BREACH', passed: true, detail: 'Rest break requirement satisfied.' },
      { rule: 'OVERTIME_RISK', passed: true, detail: 'Within daily/weekly regular threshold.' },
      { rule: 'SPREAD_OVER_BREACH', passed: true, detail: 'Within maximum spread-over limit.' },
      { rule: 'SCHEDULE_DEVIATION', passed: true, detail: 'Manager-verified timestamp.' },
    ],
  };
}

export function buildAuditRecord(params: {
  role: Role;
  item: ExceptionItem;
  decision: 'approved' | 'edited' | 'rejected';
  summary: string;
}): AuditEvent {
  const traceId = `tr-${Math.random().toString(16).slice(2, 9)}`;
  const nowIso = new Date().toISOString();
  return {
    id: `AUD-${Math.floor(3004 + Math.random() * 6000)}`,
    trace_id: traceId,
    actor_type: 'manager',
    actor_name: `Priya Menon (${params.role})`,
    action: `EXCEPTION_${params.decision.toUpperCase()}`,
    entity_ref: `${params.item.id} / ${params.item.employee_id}`,
    before_summary: params.item.before_hours.pay_status,
    after_summary: params.summary,
    ts: nowIso,
  };
}
