"""Pure shift-scoped pairing. Caller must supply the full relevant shift context."""

from dataclasses import dataclass
from datetime import timedelta

from app.attendance.contracts import AttendanceCase, Punch


@dataclass(frozen=True)
class MissingPunch:
    punch_id: str
    missing_event_type: str
    code: str = "MISSING_PUNCH"
    severity: str = "problem"


def detect_missing_punches(
    case: AttendanceCase, *, closing_grace: timedelta
) -> tuple[MissingPunch, ...]:
    """Do not flag an open shift until its scheduled end plus policy grace.

    No punches means no missing-punch inference: absence is a separate rule.
    Break events are retained in evidence but excluded from work-punch pairing.
    Equal-time work punches are ambiguous and rejected, never silently ordered.
    """
    if closing_grace < timedelta(0):
        raise ValueError("closing grace cannot be negative")
    events = sorted(
        (p for p in case.punches if p.event_type in {"in", "out"}),
        key=lambda p: p.event_time,
    )
    if len({p.event_time for p in events}) != len(events):
        raise ValueError("equal-time work punches require manual clarification")
    pending: Punch | None = None
    findings = []
    for event in events:
        if event.event_type == "in":
            if pending is not None:
                findings.append(MissingPunch(pending.id, "out"))
            pending = event
        elif pending is None:
            findings.append(MissingPunch(event.id, "in"))
        else:
            pending = None
    if pending is not None and case.as_of >= case.schedule.end + closing_grace:
        findings.append(MissingPunch(pending.id, "out"))
    return tuple(findings)


@dataclass(frozen=True)
class PairingValidation:
    missing_punch_check_passed: bool
    findings: tuple[MissingPunch, ...]
    approval_eligible: bool = False
    incomplete_checks: tuple[str, ...] = (
        "OVERLAPPING_SHIFT",
        "MEAL_BREAK_BREACH",
        "OVERTIME_RISK",
        "SPREAD_OVER_BREACH",
        "SCHEDULE_DEVIATION",
        "EVIDENCE",
        "AUTHORIZATION",
    )


def validate_added_punch(
    case: AttendanceCase, candidate: Punch, *, closing_grace: timedelta
) -> PairingValidation:
    """Simulation only. Passing pairing never authorizes a correction."""
    # Re-parse instead of model_copy(update=...), which bypasses validation.
    simulated = AttendanceCase.model_validate(
        {**case.model_dump(), "punches": (*case.punches, candidate)}
    )
    findings = detect_missing_punches(simulated, closing_grace=closing_grace)
    return PairingValidation(not findings, findings)
