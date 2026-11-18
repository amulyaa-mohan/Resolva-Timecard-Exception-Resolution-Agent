"""Shared detector-backed simulation. No writes or AI dependencies.

Correction validity only: passing never authorizes a manager to approve.
"""

from collections.abc import Callable
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# Pure note-time parser shared with Track B's gate (no model call) so both read a note alike.
from app.ai.evidence import note_times
from app.core.contracts import (
    ALLOWED_ACTIONS,
    DEFAULT_SEVERITY,
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
    RuleCheck,
    RuleOutcome,
    Severity,
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


def _evidence_anchors(
    case: CaseContext, action: ProposedAction, punch_type: PunchType
) -> list[datetime] | None:
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
        if case.schedule is None or ref.id != case.schedule.shift_id or punch_type != wanted:
            return None
        return [case.schedule.start if wanted == PunchType.IN else case.schedule.end]
    if ref.kind == EvidenceKind.NOTE:
        note = next((n for n in case.notes if n.note_id == ref.id), None)
        clock = [] if note is None else note_times(note.text)
    else:
        punch = next((p for p in case.punch_history if p.punch_id == ref.id), None)
        if punch is None or punch.type != punch_type:
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


SUPPORTED = frozenset({ActionType.ADD_PUNCH, ActionType.ADJUST_PUNCH})
MAX_ACTIONS = 2


# Paid time grows when a clock-in moves earlier, a clock-out later, a break start later or a
# break end earlier. A time the employee stated is a claim, so rounding it may only move the
# other way: never grant time nobody claimed (pay integrity, agreed with Track B 2026-11-18).
_NO_EXTRA_PAY = {
    PunchType.IN: 1,
    PunchType.OUT: -1,
    PunchType.BREAK_START: -1,
    PunchType.BREAK_END: 1,
}


def _within(
    ts: datetime,
    anchors: list[datetime],
    seconds: float,
    *,
    kind: EvidenceKind | None = None,
    punch_type: PunchType | None = None,
) -> bool:
    """Is `ts` supported by one anchor? A stated time (a note) is one-sided."""
    # Stated times (notes) and habits (same-weekday history) are one-sided: a habit of 18:00
    # must not support 18:05, which would add paid time nobody claimed (Codex finding 2).
    directional = kind in (EvidenceKind.NOTE, EvidenceKind.HISTORY_PUNCH) and (
        punch_type in _NO_EXTRA_PAY
    )
    for anchor in anchors:
        offset = (instant(ts) - instant(anchor)).total_seconds()
        if directional:
            allowed = _NO_EXTRA_PAY[punch_type] * offset
            if 0 <= allowed <= seconds:
                return True
        elif abs(offset) <= seconds:
            return True
    return False


def _check_add(case, action, policy) -> str | None:
    """Why an add_punch is unacceptable, or None. Fills a missing work punch only."""
    if case.code != ExceptionCode.MISSING_PUNCH:
        return "add_punch only repairs a missing punch."
    if action.punch_type not in (PunchType.IN, PunchType.OUT):
        return "Only a work clock-in/clock-out can repair a missing work punch."
    if action.punch_id is not None:
        return "add_punch cannot target an existing punch."
    expected = case.schedule.start if action.punch_type == PunchType.IN else case.schedule.end
    delta = abs((instant(action.new_ts) - instant(expected)).total_seconds())
    if delta > policy.rules.missing_punch_window_min * 60:
        return "Proposed timestamp exceeds the configured inference window."
    if case.as_of is not None and instant(action.new_ts) > instant(case.as_of):
        return "Proposed punch is later than the evaluation time (as_of)."
    if action.evidence_ref is None:
        # No matched evidence: only the exact scheduled boundary is acceptable.
        return (
            None
            if delta == 0
            else ("Proposed time has no evidence_ref and is not the exact schedule time.")
        )
    anchors = _evidence_anchors(case, action, action.punch_type)
    if anchors is None:
        return "evidence_ref does not resolve to supporting evidence."
    if not _within(
        action.new_ts,
        anchors,
        policy.rules.evidence_tolerance_min * 60,
        kind=action.evidence_ref.kind,
        punch_type=action.punch_type,
    ):
        return _tolerance_reason(action, policy)
    return None


def _tolerance_reason(action: ProposedAction, policy: PolicySnapshot) -> str:
    minutes = policy.rules.evidence_tolerance_min
    if action.evidence_ref.kind in (EvidenceKind.NOTE, EvidenceKind.HISTORY_PUNCH):
        return (
            f"Proposed time is not within {minutes} min of the stated or habitual time in the direction "
            "that adds no unclaimed paid time."
        )
    return f"Proposed time is more than {minutes} min from the evidence it cites."


def _check_adjust(case, action, target, policy) -> str | None:
    """Why an adjust_punch is unacceptable, or None.

    A recorded punch is itself evidence. Moving it needs the employee's own stated time
    (a note ref, within evidence_tolerance_min); a schedule or habit cannot overrule a
    recording, or late arrivals could be silently moved to the scheduled start.
    """
    if target is None:
        return "adjust_punch must target one of this case's own punches."
    if action.punch_type is not None and action.punch_type != target.type:
        return "adjust_punch cannot change a punch's type."
    if abs((instant(action.new_ts) - instant(target.ts)).total_seconds()) > (
        policy.rules.missing_punch_window_min * 60
    ):
        return "Adjustment moves the punch further than the configured window."
    if case.as_of is not None and instant(action.new_ts) > instant(case.as_of):
        return "Adjusted punch is later than the evaluation time (as_of)."
    ref = action.evidence_ref
    if ref is None or ref.kind != EvidenceKind.NOTE:
        return "Moving a recorded punch needs the employee's stated time (a note evidence_ref)."
    anchors = _evidence_anchors(case, action, target.type)
    if anchors is None:
        return "evidence_ref does not resolve to supporting evidence."
    if not _within(
        action.new_ts,
        anchors,
        policy.rules.evidence_tolerance_min * 60,
        kind=ref.kind,
        punch_type=target.type,
    ):
        return _tolerance_reason(action, policy)
    return None


def _validate(
    case: CaseContext,
    actions: list[ProposedAction],
    policy: PolicySnapshot,
    load_aggregates: AggregateLoader | None,
) -> ValidationResult:
    if case.code == ExceptionCode.MISSING_PUNCH:
        if case.schedule is None:
            return _reject(
                "No schedule to anchor a missing punch.", RuleOutcome.INSUFFICIENT_EVIDENCE
            )
        if len(actions) != 1:
            return _reject("Supported correction requires one missing-punch action.")
    elif not 1 <= len(actions) <= MAX_ACTIONS:
        return _reject(f"A correction needs 1 to {MAX_ACTIONS} actions.")
    try:
        parsed = [ProposedAction.model_validate(a.model_dump()) for a in actions]
        for action in parsed:
            if action.type not in ALLOWED_ACTIONS[case.code]:
                return _reject(f"{action.type.value} is not allowed for {case.code.value}.")
            if action.type not in SUPPORTED:
                # acknowledge / add_break / void_shift / flag_premium / schedule swap need
                # agreed semantics (contract) before they can be validated; never guessed.
                # Audit A4: cannot be judged yet, which is not the same as wrong: escalate.
                return _reject(
                    f"{action.type.value} corrections are not supported yet; manager review.",
                    RuleOutcome.INSUFFICIENT_EVIDENCE,
                )
        targets = [a.punch_id for a in parsed if a.type == ActionType.ADJUST_PUNCH]
        if len(set(targets)) != len(targets):
            return _reject("Two actions target the same punch.")
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
        if next(c for c in before if c.code == case.code).passed:
            return _reject(f"Target {case.code.value} exception is no longer present.")
        by_id = {p.punch_id: p for p in case.punches}
        punches = dict(by_id)
        for index, action in enumerate(parsed):
            if action.type == ActionType.ADD_PUNCH:
                problem = _check_add(case, action, policy)
                key = f"simulation-added-punch-{index}"
                if key in by_id or any(p.punch_id == key for p in case.punch_history):
                    problem = problem or "Simulation identity conflicts with existing evidence."
                record = PunchRecord(
                    punch_id=key,
                    employee_id=case.employee.employee_id,
                    ts=action.new_ts,
                    type=action.punch_type,
                    source=PunchSource.IMPORT,
                )
            else:
                target = by_id.get(action.punch_id)
                problem = _check_adjust(case, action, target, policy)
                key = action.punch_id
                record = None if target is None else target.model_copy(update={"ts": action.new_ts})
            if problem:
                return _reject(problem)
            punches[key] = record
        moved = [p for k, p in punches.items() if k not in by_id or p is not by_id[k]]
        others = [p for k, p in punches.items() if p not in moved]
        if any(instant(m.ts) == instant(o.ts) for m in moved for o in others):
            return _reject("Proposed punch duplicates the time of an existing punch.")
        # Simulate on a re-validated copy; the caller's raw punches are never mutated.
        simulated = CaseContext.model_validate(
            {**case.model_dump(), "punches": [p.model_dump() for p in punches.values()]}
        )
        # Every applicable rule must pass afterwards, so a fix can neither leave nor create
        # another violation (e.g. completing a shift that then exceeds weekly hours).
        checks = evaluate_rules(simulated, policy, aggregates)
        checks = _warning_needs_review(checks, parsed)
        return ValidationResult(
            passed=all(c.passed for c in checks), checks=checks, rule_version=RULE_VERSION
        )
    except (ValueError, AttributeError, KeyError) as exc:
        return _reject(f"Invalid correction evidence: {exc}", RuleOutcome.INSUFFICIENT_EVIDENCE)


def _warning_needs_review(
    checks: list[RuleCheck], actions: list[ProposedAction]
) -> list[RuleCheck]:
    """An evidenced fix whose only remaining failure is a warning goes to the manager.

    Agreed with Track B (2026-11-18): the pipeline then ESCALATES instead of BLOCKING, so a
    manager can approve or acknowledge it. Problem-severity rules keep blocking, and nothing
    here makes a correction approvable on its own.
    """
    failed = [c for c in checks if not c.passed]
    reviewable = {
        code for code, severity in DEFAULT_SEVERITY.items() if severity == Severity.WARNING
    } & {ExceptionCode.SCHEDULE_DEVIATION}
    if not all(a.evidence_ref is not None for a in actions) or len(failed) != 1:
        return checks
    if failed[0].code not in reviewable or failed[0].outcome != RuleOutcome.VIOLATION:
        return checks
    return [
        RuleCheck(
            code=c.code,
            passed=False,
            reason=f"Fix is evidenced but leaves a warning: manager review. {c.reason}",
            outcome=RuleOutcome.INSUFFICIENT_EVIDENCE,
        )
        if c is failed[0]
        else c
        for c in checks
    ]


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
