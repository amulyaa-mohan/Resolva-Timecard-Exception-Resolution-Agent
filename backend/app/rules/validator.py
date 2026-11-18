"""Track B-compatible partial validator; fails closed until full rule coverage."""

from datetime import timedelta

from app.attendance.contracts import AttendanceCase, Employee, Punch, ScheduledShift
from app.core.contracts import (
    ActionType,
    CaseContext,
    ExceptionCode,
    PolicySnapshot,
    ProposedAction,
    RuleCheck,
    ValidationResult,
)
from app.rules.missing_punch import validate_added_punch


def validate_correction(
    case: CaseContext, actions: list[ProposedAction], policy: PolicySnapshot
) -> ValidationResult:
    checks = []
    supported = (
        case.code == ExceptionCode.MISSING_PUNCH
        and case.schedule is not None
        and len(actions) == 1
        and actions[0].type == ActionType.ADD_PUNCH
    )
    if supported:
        action, shift = actions[0], case.schedule
        assert shift is not None
        try:
            context = AttendanceCase(
                employee=Employee(
                    id=case.employee.employee_id,
                    manager_id="internal-validation-only",
                    location_id=case.employee.location_id,
                    timezone=case.employee.timezone,
                ),
                schedule=ScheduledShift(
                    id=shift.shift_id,
                    employee_id=shift.employee_id,
                    start=shift.start,
                    end=shift.end,
                ),
                punches=tuple(
                    Punch(
                        id=p.punch_id,
                        employee_id=p.employee_id,
                        event_time=p.ts,
                        event_type=p.type.value,
                        source=p.source.value,
                        source_event_id=p.punch_id,
                    )
                    for p in case.punches
                ),
                evidence_version=case.evidence_version,
                # The draft has no as_of field: evaluate closed-shift pairing only.
                as_of=max([shift.end, *(p.ts for p in case.punches)]),
            )
            candidate = Punch(
                id="proposed-addition",
                employee_id=case.employee.employee_id,
                event_time=action.new_ts,
                event_type=action.punch_type.value,
                source="proposal",
                source_event_id="proposed-addition",
            )
            result = validate_added_punch(context, candidate, closing_grace=timedelta(0))
            checks.append(
                RuleCheck(
                    code=case.code,
                    passed=result.missing_punch_check_passed,
                    reason="Pairing simulation only; evidence and remaining rules pending.",
                )
            )
        except (ValueError, AttributeError) as exc:
            checks.append(
                RuleCheck(
                    code=case.code, passed=False, reason=f"Invalid attendance evidence: {exc}"
                )
            )
    else:
        checks.append(
            RuleCheck(
                code=case.code,
                passed=False,
                reason="Action or context not supported by partial validator.",
            )
        )
    for code in ExceptionCode:
        if code != case.code:
            checks.append(
                RuleCheck(
                    code=code, passed=False, reason="Rule implementation pending; approval blocked."
                )
            )
    return ValidationResult(passed=False, checks=checks, rule_version=case.rule_version)
