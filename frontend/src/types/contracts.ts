export type Severity = 'problem' | 'warning';
// 'proposed' is a UI-only state: the backend knows open | escalated | resolved, and the UI
// marks an item 'proposed' once an eligible draft has been fetched for it.
export type ExceptionStatus = 'open' | 'proposed' | 'escalated' | 'resolved';
export type DecisionType = 'approved' | 'edited' | 'rejected';
export type Role = 'employee' | 'manager' | 'payroll_admin' | 'compliance' | 'admin';
export type UILang = 'en' | 'hi';

export interface PunchEvent {
  id: string;
  employee_id: string;
  ts: string;
  type: 'in' | 'out' | 'break_start' | 'break_end';
  source: 'kiosk' | 'mobile' | 'badge' | 'web' | 'import';
  device_id: string;

  source?: 'kiosk' | 'mobile' | 'badge' | 'web' | 'import' | string;
  device_id?: string;
}

export interface ScheduleShift {
  id: string;
  employee_id: string;
  start: string;
  end: string;
  planned_break_min: number;
  location: string;
  job: string;
}

export interface HoursSummary {
  regular_hours: string;
  overtime_hours: string;
  pay_status: string;
}

export interface EvidenceRef {
  kind: 'schedule_start' | 'schedule_end' | 'note' | 'history_punch';
  id: string;
}

/** Mirrors the backend ActionType. The older UI-only names are kept for the demo fixtures. */
export interface ProposedAction {
  type:
    | 'add_punch'
    | 'adjust_punch'
    | 'void_shift'
    | 'add_break'
    | 'flag_premium'
    | 'suggest_schedule_swap'
    | 'acknowledge'
    | 'edit_punch'
    | 'waive_warning'
    | 'escalate';
  punch_id?: string;
  punch_type?: 'in' | 'out' | 'break_start' | 'break_end';
  target_punch_id?: string;
  new_ts?: string;
  note: string;
  /** Which evidence supports new_ts. Attached by the backend, never invented here. */
  evidence_ref?: EvidenceRef | null;
}

export interface Citation {
  chunk_id: string;
  quote: string;
}

export interface RuleOutcome {
  rule: string;
  passed: boolean;
  detail: string;
  /** pass | violation | insufficient_evidence. Absent on demo fixtures. */
  outcome?: string;
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
  evidence_version: string;
  validator_passed: boolean;
  rule_outcomes: RuleOutcome[];
}

export interface ResolutionRecord {
  decision: DecisionType;
  decided_by: string;
  reason_code?: string;
  comment?: string;
  decided_at: string;
  trace_id: string;
}

export interface ExceptionItem {
  id: string;
  code: string;
  severity: Severity;
  employee_id: string;
  employee_name: string;
  job: string;
  location: string;
  timezone: string;
  policy_pack_id: string;
  work_date: string;
  status: ExceptionStatus;
  evidence_version: string;
  stale_warning?: boolean;
  summary: string;
  employee_note?: string;
  schedule?: ScheduleShift;
  punches: PunchEvent[];
  before_hours: HoursSummary;
  after_hours?: HoursSummary;
  proposal?: LLMProposal;
  /** What the backend pipeline returned for the last draft: eligible, blocked or escalated. */
  draft_status?: 'eligible' | 'blocked' | 'escalated';
  draft_reasons?: string[];
  resolution?: ResolutionRecord;
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
  model_id?: string;
  evidence_hash?: string;
  decision_id?: string | null;
}

export interface PolicyPack {
  id: string;
  version: string;
  jurisdiction: string;
  daily_regular_hours: number;
  weekly_regular_hours: number;
  overtime_rate: number;
  quarterly_ot_cap?: number | null;
  rest_minutes: number;
  rest_after_hours: number;
  max_spread_hours?: number | null;
  late_tolerance_min?: number;
}

export interface ImportRow {
  row_num: number;
  employee_id: string;
  employee_name: string;
  work_date: string;
  in_time: string;
  out_time: string;
  location: string;
  valid: boolean;
  error?: string;
}



