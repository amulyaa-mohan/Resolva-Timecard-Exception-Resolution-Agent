"""Shared integration contracts between Track A and Track B (SHARED-01).

STATUS: DRAFT PROPOSAL (contract version below). Drafted by Amulya (Track B) for
review by C V Jayanth (Track A). Do not treat as frozen until both developers
agree and docs/TASKS.md marks SHARED-01 as DONE.

Ownership of the functions these models flow through:

    build_case_context(exception_id) -> CaseContext                         (A)
    resolve_policy(employee, work_date) -> PolicySnapshot                    (B)
    generate_proposal(case, policy, ...) -> ProposalResult                   (B)
    validate_correction(case, actions, policy) -> ValidationResult           (A)
    record_audit(event) -> AuditEvent                                        (A)

Design rules encoded here:
- Every timestamp is timezone-aware (naive datetimes are rejected).
- All contract models are immutable and reject unknown fields.
- An escalation is representable without fabricated actions or citations.
- The LLM may only propose actions allowed for the exception code.

0.2.0-draft (agreed in TRACK_A_CONTRACT_RESPONSE.md and Track B's reply, 2026-11-18):
- RuleCheck.outcome: pass / violation / insufficient_evidence. A violation blocks the
  proposal; insufficient evidence escalates it to the manager. Neither is approval-ready.
- ProposedAction.evidence_ref: the schedule time, note or history punch a proposed time
  comes from. Attached by Track B's deterministic gate, never trusted from the model.
- PolicyRules: evidence_tolerance_min, week_start, quarter_start_month.
- CaseContext.as_of: when the case was evaluated, so open shifts are not treated as
  overdue. Excluded from evidence_version.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, model_validator

CONTRACT_VERSION = "0.2.0-draft"


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- enums


class ExceptionCode(StrEnum):
    MISSING_PUNCH = "MISSING_PUNCH"
    OVERLAPPING_SHIFT = "OVERLAPPING_SHIFT"
    MEAL_BREAK_BREACH = "MEAL_BREAK_BREACH"
    OVERTIME_RISK = "OVERTIME_RISK"
    SPREAD_OVER_BREACH = "SPREAD_OVER_BREACH"
    SCHEDULE_DEVIATION = "SCHEDULE_DEVIATION"


class Severity(StrEnum):
    PROBLEM = "problem"  # blocks pay
    WARNING = "warning"  # payable, needs review


class PunchType(StrEnum):
    IN = "in"
    OUT = "out"
    BREAK_START = "break_start"
    BREAK_END = "break_end"


class PunchSource(StrEnum):
    KIOSK = "kiosk"
    MOBILE = "mobile"
    WEB = "web"
    IMPORT = "import"


class ActionType(StrEnum):
    ADD_PUNCH = "add_punch"
    ADJUST_PUNCH = "adjust_punch"
    VOID_SHIFT = "void_shift"
    ADD_BREAK = "add_break"
    FLAG_PREMIUM = "flag_premium"
    SUGGEST_SCHEDULE_SWAP = "suggest_schedule_swap"
    ACKNOWLEDGE = "acknowledge"


class Weekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

    @property
    def number(self) -> int:
        """Python weekday number (Monday = 0), as returned by date.weekday()."""
        return list(Weekday).index(self)


class RuleOutcome(StrEnum):
    PASS = "pass"
    VIOLATION = "violation"  # the correction breaks the rule -> BLOCKED
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # cannot be decided -> ESCALATED


class EvidenceKind(StrEnum):
    SCHEDULE_START = "schedule_start"  # id = shift_id
    SCHEDULE_END = "schedule_end"  # id = shift_id
    NOTE = "note"  # id = note_id; the time is the one the employee stated
    HISTORY_PUNCH = "history_punch"  # id = punch_id in punch_history (same weekday)


DEFAULT_SEVERITY: dict[ExceptionCode, Severity] = {
    ExceptionCode.MISSING_PUNCH: Severity.PROBLEM,
    ExceptionCode.OVERLAPPING_SHIFT: Severity.PROBLEM,
    ExceptionCode.MEAL_BREAK_BREACH: Severity.WARNING,
    ExceptionCode.OVERTIME_RISK: Severity.WARNING,
    ExceptionCode.SPREAD_OVER_BREACH: Severity.PROBLEM,
    ExceptionCode.SCHEDULE_DEVIATION: Severity.WARNING,
}

# Actions the LLM may propose per exception code (design doc section 8).
# Anything else is rejected by the evidence gate before validation.
ALLOWED_ACTIONS: dict[ExceptionCode, frozenset[ActionType]] = {
    ExceptionCode.MISSING_PUNCH: frozenset({ActionType.ADD_PUNCH}),
    ExceptionCode.OVERLAPPING_SHIFT: frozenset({ActionType.VOID_SHIFT, ActionType.ADJUST_PUNCH}),
    ExceptionCode.MEAL_BREAK_BREACH: frozenset({ActionType.ADD_BREAK, ActionType.FLAG_PREMIUM}),
    ExceptionCode.OVERTIME_RISK: frozenset(
        {ActionType.SUGGEST_SCHEDULE_SWAP, ActionType.ACKNOWLEDGE}
    ),
    ExceptionCode.SPREAD_OVER_BREACH: frozenset({ActionType.ADJUST_PUNCH}),
    ExceptionCode.SCHEDULE_DEVIATION: frozenset({ActionType.ACKNOWLEDGE, ActionType.ADJUST_PUNCH}),
}


# ------------------------------------------------------------ case context (A -> B)


class EmployeeContext(_Contract):
    employee_id: str
    location_id: str
    jurisdiction: str = Field(description="Policy jurisdiction id, e.g. 'IN-KA' or 'US-FED'.")
    timezone: str = Field(description="IANA timezone of the work location, e.g. 'Asia/Kolkata'.")
    worker_category: str | None = None


class PunchRecord(_Contract):
    """Raw punch evidence. Raw punches are immutable; corrections are separate records."""

    punch_id: str
    employee_id: str
    ts: AwareDatetime
    type: PunchType
    source: PunchSource
    device_id: str | None = None


class ScheduledShift(_Contract):
    shift_id: str
    employee_id: str
    start: AwareDatetime
    end: AwareDatetime
    planned_break_min: int = Field(ge=0)

    @model_validator(mode="after")
    def _end_after_start(self) -> ScheduledShift:
        if self.end <= self.start:
            raise ValueError("scheduled shift end must be after start")
        return self


class EmployeeNote(_Contract):
    """Free text written by the employee. Untrusted: evidence, never instructions."""

    note_id: str
    text: str = Field(max_length=1000)
    submitted_at: AwareDatetime


DetailValue = str | int | float | bool | None


class CaseContext(_Contract):
    """Everything the AI pipeline may see about one exception. Built by Track A."""

    exception_id: str
    code: ExceptionCode
    severity: Severity
    employee: EmployeeContext
    work_date: date
    rule_version: str
    punches: list[PunchRecord] = Field(description="Raw punches for the work date.")
    punch_history: list[PunchRecord] = Field(
        default_factory=list, description="Raw punches for the previous 7 days."
    )
    schedule: ScheduledShift | None = None
    notes: list[EmployeeNote] = Field(default_factory=list)
    detection_details: dict[str, DetailValue] = Field(default_factory=dict)
    evidence_version: str = Field(
        description="Opaque hash of the evidence above; approval rejects a stale version."
    )
    as_of: AwareDatetime | None = Field(
        default=None,
        description=(
            "When the case was evaluated (server clock). A shift still open at this time is "
            "not overdue, and no correction may add a punch after it. Not part of "
            "evidence_version. Optional during 0.2.0-draft; Track A's CaseService sets it."
        ),
    )


# ------------------------------------------------------------ policy snapshot (B)


class PolicyRules(_Contract):
    """Structured thresholds. The deterministic rules use these, never retrieved text."""

    daily_regular_hours: float = Field(gt=0)
    weekly_regular_hours: float = Field(gt=0)
    max_spread_hours: float | None = Field(default=None, gt=0)
    overtime_rate: float = Field(ge=1)
    quarterly_ot_cap_hours: float | None = Field(default=None, gt=0)
    rest_after_hours: float = Field(gt=0)
    rest_minutes: int = Field(ge=0)
    late_tolerance_min: int = Field(ge=0)
    missing_punch_window_min: int = Field(ge=0)
    evidence_tolerance_min: int = Field(
        ge=0,
        le=60,
        description="How far a proposed time may be from the evidence its evidence_ref names.",
    )
    week_start: Weekday = Field(description="First day of the policy week (weekly limits).")
    quarter_start_month: int = Field(
        ge=1,
        le=12,
        description="Month a quarter starts in (1 = calendar quarters Jan/Apr/Jul/Oct).",
    )


class PolicyClause(_Contract):
    chunk_id: str = Field(description="Stable id '<pack_id>@<version>#<clause_id>'.")
    pack_id: str
    version: str
    clause_id: str
    title: str
    text: str


class PolicySnapshot(_Contract):
    pack_id: str
    version: str
    jurisdiction: str
    status: Literal["active", "proposed", "retired"]
    effective_from: date
    effective_to: date | None = None
    rules: PolicyRules
    clauses: list[PolicyClause]
    content_hash: str


# ------------------------------------------------------------ LLM output contract


class EvidenceRef(_Contract):
    """The evidence a proposed time comes from. Resolved against the CaseContext."""

    kind: EvidenceKind
    id: str = Field(min_length=1, description="shift_id, note_id or punch_id, per kind.")


class ProposedAction(_Contract):
    type: ActionType
    punch_id: str | None = Field(default=None, description="Existing punch to adjust.")
    punch_type: PunchType | None = Field(default=None, description="Type of a punch to add.")
    new_ts: AwareDatetime | None = None
    note: str = Field(default="", max_length=200)
    evidence_ref: EvidenceRef | None = Field(
        default=None,
        description=(
            "Evidence for new_ts. Set by Track B's deterministic time-evidence gate; a "
            "model-supplied ref is only kept if it resolves and matches. None means no "
            "evidence was matched, and the validator must then treat the time strictly."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _null_note_is_empty(cls, data):
        # Live Qwen2.5-7B writes "note": null; rejecting it cost a repair retry and pushed the
        # injection case x08 past the 8 s budget. An absent note carries no meaning either way.
        if isinstance(data, dict) and "note" in data and data["note"] is None:
            data = {**data, "note": ""}
        return data

    @model_validator(mode="after")
    def _required_fields(self) -> ProposedAction:
        if self.type == ActionType.ADD_PUNCH and (self.new_ts is None or self.punch_type is None):
            raise ValueError("add_punch requires new_ts and punch_type")
        if self.type == ActionType.ADJUST_PUNCH and (self.punch_id is None or self.new_ts is None):
            raise ValueError("adjust_punch requires punch_id and new_ts")
        return self


class Citation(_Contract):
    chunk_id: str = Field(description="Must exist in the retrieved set for this request.")
    quote: str = Field(max_length=300)


class LLMProposal(_Contract):
    exception_id: str
    decision: Literal["propose", "escalate"]
    actions: list[ProposedAction] = Field(default_factory=list)
    rationale: str = Field(max_length=600)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _decision_shape(self) -> LLMProposal:
        if self.decision == "propose":
            if not self.actions:
                raise ValueError("a proposal needs at least one action")
            if not self.citations:
                raise ValueError("a proposal needs at least one citation")
        elif self.actions:
            raise ValueError("an escalation must not carry actions")
        return self


# ------------------------------------------------------------ validation (A -> B)


_BOOL = TypeAdapter(bool)


class RuleCheck(_Contract):
    """One rule's verdict. `outcome` may be omitted: it is then derived from `passed`
    (True -> pass, False -> violation). When both are given they must agree."""

    code: ExceptionCode
    passed: bool
    reason: str
    outcome: RuleOutcome

    @model_validator(mode="before")
    @classmethod
    def _derive_outcome(cls, data):
        if isinstance(data, dict) and data.get("outcome") is None and "passed" in data:
            try:  # same coercion as the field itself (e.g. JSON "true")
                passed = _BOOL.validate_python(data["passed"])
            except ValueError:
                return data  # the field validation reports the bad value
            data = {**data, "outcome": RuleOutcome.PASS if passed else RuleOutcome.VIOLATION}
        return data

    @model_validator(mode="after")
    def _consistent(self) -> RuleCheck:
        if self.passed != (self.outcome == RuleOutcome.PASS):
            raise ValueError("passed must be true exactly when outcome is 'pass'")
        return self


class ValidationResult(_Contract):
    passed: bool
    checks: list[RuleCheck]
    rule_version: str

    @model_validator(mode="after")
    def _passed_needs_passing_checks(self) -> ValidationResult:
        if self.passed and (not self.checks or not all(c.passed for c in self.checks)):
            raise ValueError("passed=true needs at least one check and every check passing")
        return self


class CorrectionValidator(Protocol):
    """Track A's validate_correction. Reuses the exact detection rule functions."""

    def __call__(
        self, case: CaseContext, actions: list[ProposedAction], policy: PolicySnapshot
    ) -> ValidationResult: ...


# ------------------------------------------------------------ pipeline result (B -> A)


class GateStatus(StrEnum):
    ELIGIBLE = "eligible"  # every gate passed; a manager may approve (and bulk-approve)
    BLOCKED = "blocked"  # the model proposed, but a deterministic check failed
    ESCALATED = "escalated"  # no safe proposal: refused, missing evidence, or AI unavailable


class GateCheck(_Contract):
    name: str
    passed: bool
    detail: str = ""


class LLMTrace(_Contract):
    trace_id: str
    provider: str
    model_id: str | None
    prompt_version: str
    prompt_hash: str | None
    retrieved_chunk_ids: list[str]
    raw_outputs: list[str]
    parse_errors: list[str]
    attempts: int
    latency_ms: int
    error: str | None = None


class ProposalResult(_Contract):
    exception_id: str
    status: GateStatus
    proposal: LLMProposal | None
    validation: ValidationResult | None
    gate_checks: list[GateCheck]
    reasons: list[str] = Field(description="Human-readable reasons when not eligible.")
    policy_pack_id: str | None
    policy_version: str | None
    evidence_version: str
    trace: LLMTrace
