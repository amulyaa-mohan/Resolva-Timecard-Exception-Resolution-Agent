"""Shared detector-backed simulation. No writes or AI dependencies.

Correction validity only: passing never authorizes a manager to approve.
"""

from collections.abc import Callable
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# Pure note-time parser shared with Track B's gate (no model call) so both read a note alike.
from app.ai.evidence import note_times
from app.core.contracts import (
    ActionType,
    CaseContext,
    CorrectionValidator,
    EvidenceKind,
    ExceptionCode,
    PolicySnapshot,
    ProposedAction,
    PunchRecord,
    PunchSource,
    PunchType,
    RuleOutcome,
    ValidationResult,
)
from app.rules.engine import (
    RULE_VERSION,
    AggregateEvidence,
    blocked_checks,
    evaluate_rules,
    instant,
)

# Trusted backend source of other-day totals, keyed by the case's own identifiers.
# Never wire it to model output, client input or detection_details. Returning None
# means "not available" and keeps the overtime check failed closed.
AggregateLoader = Callable[[CaseContext], AggregateEvidence | None]


def _reject(reason: str, outcome: RuleOutcome = RuleOutcome.VIOLATION) -> ValidationResult:
    """Unsupported or unsafe corrections are violations (BLOCKED). Only inputs that cannot
    be decided (no schedule, unreadable evidence, totals unavailable) are insufficient."""
    return ValidationResult(
        passed=False, checks=blocked_checks(reason, outcome), rule_version=RULE_VERSION
    )


def _evidence_anchors(case: CaseContext, action: ProposedAction) -> list[datetime] | None:
    """Times the action's evidence_ref supports, or None if the ref does not resolve.

    Mirrors Track B's time-evidence gate (contract 0.2.0): schedule refs give the exact
    boundary for the matching punch type; a note gives each clock time the employee stated,
    and a same-weekday history punch of the same type gives its clock time, both on the
    work date or the next day in the employee's timezone.
    """
    ref = action.evidence_ref
    zone = ZoneInfo(case.employee.timezone)
    if ref.kind in (EvidenceKind.SCHEDULE_START, EvidenceKind.SCHEDULE_END):
        wanted = PunchType.IN if ref.kind == EvidenceKind.SCHEDULE_START else PunchType.OUT
        if case.schedule is None or ref.id != case.schedule.shift_id or action.punch_type != wanted:
            return None
        return [case.schedule.start if wanted == PunchType.IN else case.schedule.end]
    if ref.kind == EvidenceKind.NOTE:
        note = next((n for n in case.notes if n.note_id == ref.id), None)
        clock = [] if note is None else note_times(note.text)
    else:
        punch = next((p for p in case.punch_history if p.punch_id == ref.id), None)
        if punch is None or punch.type != action.punch_type:
            return None
        local = punch.ts.astimezone(zone)
        if local.weekday() != case.work_date.weekday():
            return None
        clock = [(local.hour, local.minute)]
    if not clock:
        return None
    return [
        datetime.combine(case.work_date + timedelta(days=d), time(h, m), tzinfo=zone)
        for h, m in clock
        for d in (0, 1)
    ]


def _validate(
    case: CaseContext,
    actions: list[ProposedAction],
    policy: PolicySnapshot,
    load_aggregates: AggregateLoader | None,
) -> ValidationResult:
    # Other actions await agreed target/evidence fields; never invent them.
    if case.schedule is None:
        return _reject("No schedule to anchor a missing punch.", RuleOutcome.INSUFFICIENT_EVIDENCE)
    if case.code != ExceptionCode.MISSING_PUNCH or len(actions) != 1:
        return _reject("Supported correction requires one missing-punch action.")
    try:
        action = ProposedAction.model_validate(actions[0].model_dump())
        if action.type != ActionType.ADD_PUNCH or action.punch_type not in (
            PunchType.IN,
            PunchType.OUT,
        ):
            return _reject("Only a work clock-in/clock-out can repair a missing work punch.")
        if action.punch_id is not None:
            return _reject("add_punch cannot target an existing punch.")
        aggregates = None
        if load_aggregates is not None:
            try:
                aggregates = load_aggregates(case)
            except Exception as exc:  # a broken source must fail closed, not pass
                return _reject(
                    f"Trusted aggregate evidence unavailable: {type(exc).__name__}.",
                    RuleOutcome.INSUFFICIENT_EVIDENCE,
                )
            if aggregates is not None and not isinstance(aggregates, AggregateEvidence):
                return _reject(
                    "Aggregate source returned an unsupported value.",
                    RuleOutcome.INSUFFICIENT_EVIDENCE,
                )
        before = evaluate_rules(case, policy, aggregates)
        if next(c for c in before if c.code == ExceptionCode.MISSING_PUNCH).passed:
            return _reject("Target missing-punch exception is no longer present.")
        expected = case.schedule.start if action.punch_type == PunchType.IN else case.schedule.end
        delta = abs((instant(action.new_ts) - instant(expected)).total_seconds())
        if delta > policy.rules.missing_punch_window_min * 60:
            return _reject("Proposed timestamp exceeds the configured inference window.")
        if case.as_of is not None and instant(action.new_ts) > instant(case.as_of):
            return _reject("Proposed punch is later than the evaluation time (as_of).")
        if action.evidence_ref is None:
            # No matched evidence: only the exact scheduled boundary is acceptable.
            if delta != 0:
                return _reject(
                    "Proposed time has no evidence_ref and is not the exact schedule time."
                )
        else:
            anchors = _evidence_anchors(case, action)
            if anchors is None:
                return _reject("evidence_ref does not resolve to supporting evidence.")
            tolerance = policy.rules.evidence_tolerance_min * 60
            if not any(
                abs((instant(action.new_ts) - instant(a)).total_seconds()) <= tolerance
                for a in anchors
            ):
                return _reject(
                    f"Proposed time is more than {policy.rules.evidence_tolerance_min} min "
                    "from the evidence it cites."
                )
        if any(instant(p.ts) == instant(action.new_ts) for p in case.punches):
            return _reject("Proposed punch duplicates the time of an existing punch.")
        candidate_id = "simulation-added-punch"
        if any(p.punch_id == candidate_id for p in case.punches + case.punch_history):
            return _reject("Simulation identity conflicts with existing evidence.")
        candidate = PunchRecord(
            punch_id=candidate_id,
            employee_id=case.employee.employee_id,
            ts=action.new_ts,
            type=action.punch_type,
            source=PunchSource.IMPORT,
        )
        # Simulate on a re-validated copy; the caller's raw punches are never mutated.
        simulated = CaseContext.model_validate(
            {**case.model_dump(), "punches": [*case.punches, candidate]}
        )
        # Every applicable rule must pass afterwards, so a fix can neither leave nor create
        # another violation (e.g. completing a shift that then exceeds weekly hours).
        checks = evaluate_rules(simulated, policy, aggregates)
        return ValidationResult(
            passed=all(c.passed for c in checks), checks=checks, rule_version=RULE_VERSION
        )
    except (ValueError, AttributeError, KeyError) as exc:
        return _reject(f"Invalid correction evidence: {exc}", RuleOutcome.INSUFFICIENT_EVIDENCE)


def validate_correction(
    case: CaseContext, actions: list[ProposedAction], policy: PolicySnapshot
) -> ValidationResult:
    """Default validator: no aggregate source, so overtime and approval stay failed closed."""
    return _validate(case, actions, policy, None)


def make_validator(load_aggregates: AggregateLoader) -> CorrectionValidator:
    """Bind a trusted aggregate source while keeping the shared three-argument interface.

    The pipeline still calls validator(case, actions, policy); no contract field changes.
    """

    def validator(
        case: CaseContext, actions: list[ProposedAction], policy: PolicySnapshot
    ) -> ValidationResult:
        return _validate(case, actions, policy, load_aggregates)

    return validator
