export type Role = 'manager' | 'employee' | 'payroll_admin' | 'compliance' | 'admin';

export type Severity = 'problem' | 'warning';

export type ExceptionCode =
  | 'MISSING_PUNCH'
  | 'OVERLAPPING_SHIFT'
  | 'MEAL_BREAK_BREACH'
  | 'OVERTIME_RISK'
  | 'SPREAD_OVER_BREACH'
  | 'SCHEDULE_DEVIATION';

export type ExceptionStatus = 'open' | 'proposed' | 'escalated' | 'resolved';

export type ActionType =
  | 'add_punch'
  | 'adjust_punch'
  | 'void_shift'
  | 'add_break'
  | 'flag_premium'
  | 'suggest_schedule_swap'
  | 'acknowledge';

export interface ScheduledShift {
  id: string;
  employee_id: string;
  start: string;
  end: string;
  planned_break_min: number;
  location: string;
  job: string;
}

export interface Punch {
  id: string;
  employee_id: string;
  ts: string;
  type: 'in' | 'out' | 'break_start' | 'break_end';
  source: 'kiosk' | 'mobile' | 'web';
  device_id: string;
}

export interface ProposedAction {
  type: ActionType;
  punch_id?: string | null;
  new_ts?: string | null;
  note: string;
}

export interface Citation {
  chunk_id: string;
  quote: string;
}

export interface RuleOutcome {
  rule: ExceptionCode;
  passed: boolean;
  detail: string;
}

export interface LLMProposal {
  id: string;
  exception_id: string;
  decision: 'propose' | 'escalate';
  actions: ProposedAction[];
  rationale: string;
  citations: Citation[];
  confidence: number;
  missing_information: string[];
  model_id: string;
  prompt_hash: string;
  evidence_version: number;
  validator_passed: boolean;
  rule_outcomes: RuleOutcome[];
}

export interface HoursSummary {
  regular_hours: string;
  overtime_hours: string;
  pay_status: string;
}

export interface ExceptionItem {
  id: string;
  code: ExceptionCode;
  severity: Severity;
  employee_id: string;
  employee_name: string;
  job: string;
  location: string;
  timezone: string;
  policy_pack_id: string;
  work_date: string;
  status: ExceptionStatus;
  evidence_version: number;
  summary: string;
  employee_note?: string;
  schedule?: ScheduledShift;
  punches: Punch[];
  before_hours: HoursSummary;
  after_hours?: HoursSummary;
  proposal?: LLMProposal;
  resolution?: {
    decision: 'approved' | 'edited' | 'rejected';
    decided_by: string;
    reason_code?: string;
    comment?: string;
    decided_at: string;
    trace_id: string;
  };
}

export interface AuditEvent {
  id: string;
  trace_id: string;
  actor_type: 'system' | 'ai' | 'manager';
  actor_name: string;
  action: string;
  entity_ref: string;
  before_summary: string;
  after_summary: string;
  ts: string;
}

export interface PolicyPack {
  id: string;
  version: string;
  jurisdiction: string;
  daily_regular_hours: number;
  weekly_regular_hours: number;
  overtime_rate: number;
  quarterly_ot_cap: number | null;
  rest_after_hours: number;
  rest_minutes: number;
  max_spread_hours: number | null;
  late_tolerance_min: number;
}
