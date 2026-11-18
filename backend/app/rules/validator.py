"""Shared detector-backed simulation. No writes or AI dependencies.

Correction validity only: passing never authorizes a manager to approve.
"""

from collections.abc import Callable

from app.core.contracts import (
    ActionType,
    CaseContext,
    CorrectionValidator,
    ExceptionCode,
    PolicySnapshot,
    ProposedAction,
    PunchRecord,
    PunchSource,
    PunchType,
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


def _reject(reason: str) -> ValidationResult:
    return ValidationResult(passed=False, checks=blocked_checks(reason), rule_version=RULE_VERSION)


def _validate(
    case: CaseContext,
    actions: list[ProposedAction],
    policy: PolicySnapshot,
    load_aggregates: AggregateLoader | None,
) -> ValidationResult:
    # Other actions await agreed target/evidence fields; never invent them.
    if case.code != ExceptionCode.MISSING_PUNCH or len(actions) != 1 or case.schedule is None:
        return _reject("Supported correction requires one missing-punch action and a schedule.")
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
                return _reject(f"Trusted aggregate evidence unavailable: {type(exc).__name__}.")
            if aggregates is not None and not isinstance(aggregates, AggregateEvidence):
                return _reject("Aggregate source returned an unsupported value.")
        before = evaluate_rules(case, policy, aggregates)
        if next(c for c in before if c.code == ExceptionCode.MISSING_PUNCH).passed:
            return _reject("Target missing-punch exception is no longer present.")
        expected = case.schedule.start if action.punch_type == PunchType.IN else case.schedule.end
        delta = abs((instant(action.new_ts) - instant(expected)).total_seconds())
        if delta > policy.rules.missing_punch_window_min * 60:
            return _reject("Proposed timestamp exceeds the configured inference window.")
        # Until independent confirmed-time evidence is contracted, schedule is the only anchor.
        # A note or an LLM rationale does not authorize arbitrary times inside the window.
        if delta != 0:
            return _reject(
                "Proposed time requires verified evidence beyond the exact schedule anchor."
            )
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
        return _reject(f"Invalid correction evidence: {exc}")


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
