"""Synthetic test data builders. No real employee data."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.core.contracts import (
    CaseContext,
    EmployeeContext,
    EmployeeNote,
    ExceptionCode,
    PunchRecord,
    PunchSource,
    PunchType,
    RuleCheck,
    ScheduledShift,
    Severity,
    ValidationResult,
)

IST = timezone(timedelta(hours=5, minutes=30))
WORK_DATE = date(2026, 11, 12)


def make_case(*, schedule: bool = True, notes: tuple[str, ...] = ()) -> CaseContext:
    employee = EmployeeContext(
        employee_id="E-001", location_id="BLR-01", jurisdiction="IN-KA", timezone="Asia/Kolkata"
    )
    punch_in = PunchRecord(
        punch_id="P-1",
        employee_id="E-001",
        ts=datetime(2026, 11, 12, 9, 2, tzinfo=IST),
        type=PunchType.IN,
        source=PunchSource.KIOSK,
        device_id="K-7",
    )
    shift = ScheduledShift(
        shift_id="S-1",
        employee_id="E-001",
        start=datetime(2026, 11, 12, 9, 0, tzinfo=IST),
        end=datetime(2026, 11, 12, 18, 0, tzinfo=IST),
        planned_break_min=60,
    )
    return CaseContext(
        exception_id="X-1",
        code=ExceptionCode.MISSING_PUNCH,
        severity=Severity.PROBLEM,
        employee=employee,
        work_date=WORK_DATE,
        rule_version="rules@0.1",
        punches=[punch_in],
        schedule=shift if schedule else None,
        notes=[
            EmployeeNote(note_id=f"N-{i}", text=t, submitted_at=datetime(2026, 11, 13, tzinfo=IST))
            for i, t in enumerate(notes)
        ],
        detection_details={"unmatched_punch_id": "P-1"},
        evidence_version="ev-abc123",
    )


def passing_validator(case, actions, policy) -> ValidationResult:
    return ValidationResult(
        passed=True,
        checks=[RuleCheck(code=case.code, passed=True, reason="resolved")],
        rule_version="stub",
    )


def failing_validator(case, actions, policy) -> ValidationResult:
    return ValidationResult(
        passed=False,
        checks=[
            RuleCheck(code=case.code, passed=True, reason="resolved"),
            RuleCheck(
                code=ExceptionCode.SPREAD_OVER_BREACH, passed=False, reason="spread 13h > 12h"
            ),
        ],
        rule_version="stub",
    )
