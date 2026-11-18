"""STAND-IN validator for evaluation until Track A's validate_correction (A-02) exists.

It is deliberately narrow: an add_punch must fall inside the policy's missing-punch inference
window around the scheduled start or end, and the resulting punches must pair up. It is NOT the
shared rules engine and must be replaced by `validate_correction` when A-02 lands; reports say
which validator was used.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.contracts import (
    ActionType,
    CaseContext,
    PolicySnapshot,
    ProposedAction,
    PunchType,
    RuleCheck,
    ValidationResult,
)

NAME = "stub-window-v1 (stand-in until A-02)"


def window_validator(
    case: CaseContext, actions: list[ProposedAction], policy: PolicySnapshot
) -> ValidationResult:
    window = timedelta(minutes=policy.rules.missing_punch_window_min)
    checks: list[RuleCheck] = []
    types = [p.type for p in case.punches]
    for action in actions:
        if action.type != ActionType.ADD_PUNCH:
            continue  # not modelled by the stand-in: produces no check, so the pipeline blocks
        if case.schedule is None or action.new_ts is None:
            checks.append(RuleCheck(code=case.code, passed=False, reason="no schedule to anchor"))
            continue
        anchor = case.schedule.end if action.punch_type == PunchType.OUT else case.schedule.start
        inside = abs(action.new_ts - anchor) <= window
        checks.append(
            RuleCheck(
                code=case.code,
                passed=inside,
                reason=f"{action.new_ts.isoformat()} is "
                f"{'inside' if inside else 'outside'} {window} of {anchor.isoformat()}",
            )
        )
        types.append(action.punch_type)
    if checks:
        paired = types.count(PunchType.IN) == types.count(PunchType.OUT)
        checks.append(
            RuleCheck(
                code=case.code,
                passed=paired,
                reason="clock-ins and clock-outs pair up" if paired else "punches still unpaired",
            )
        )
    return ValidationResult(passed=all(c.passed for c in checks), checks=checks, rule_version=NAME)
