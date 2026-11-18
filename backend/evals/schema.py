"""Labelled evaluation case format (B-05).

Cases are compact, human-reviewable JSON (local wall-clock times, day offsets) that build into the
shared `CaseContext` contract. All data is synthetic.

Evidence is complete by default, so Track A's real validator can judge every rule:
- an observed meal break (break_start/break_end punches) 4 h into the scheduled shift;
- trusted weekly and quarterly totals (`AggregateSpec`, served by `evals/aggregates.py`);
- an evaluation time `as_of` after the shift (next day 12:00 local).
A case opts out explicitly (`observed_break: false`, `aggregates: null`, `as_of`) to test what
happens when evidence is missing.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.contracts import (
    DEFAULT_SEVERITY,
    CaseContext,
    EmployeeContext,
    EmployeeNote,
    ExceptionCode,
    PunchRecord,
    PunchSource,
    PunchType,
    ScheduledShift,
)

CASES_DIR = Path(__file__).resolve().parent / "cases"

# Fixed offsets keep cases reproducible (no DST lookups). Work dates are in November.
JURISDICTIONS: dict[str, tuple[str, timezone]] = {
    "IN-KA": ("Asia/Kolkata", timezone(timedelta(hours=5, minutes=30))),
    "US-FED": ("America/Chicago", timezone(timedelta(hours=-6))),
}
WORK_DATE = date(2026, 11, 12)  # a Thursday


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PunchSpec(_Spec):
    type: PunchType
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    day: int = Field(default=0, description="Day offset from the work date (overnight shifts).")


class TimeSpec(_Spec):
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    day: int = 0


class AggregateSpec(_Spec):
    """Trusted other-day totals for Track A's rules. Defaults: a light, in-limit week."""

    work_date_complete: bool = True
    week_other_worked_hours: float = 16.0
    week_remaining_scheduled_hours: float = 8.0
    quarter_other_overtime_hours: float = 4.0
    week_offset_days: int = Field(
        default=0, description="Shift the reported week start (non-zero = totals for another week)."
    )


class ShiftSpec(_Spec):
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_day: int = 0
    break_min: int = 60


class InputSpec(_Spec):
    code: ExceptionCode = ExceptionCode.MISSING_PUNCH
    jurisdiction: Literal["IN-KA", "US-FED"] = "IN-KA"
    punches: list[PunchSpec]
    history_days_ago: list[int] = Field(
        default_factory=list, description="Days ago with a normal schedule-time in/out pair."
    )
    schedule: ShiftSpec | None = None
    notes: list[str] = Field(default_factory=list)
    observed_break: bool = Field(
        default=True,
        description="Add break_start/break_end punches 4 h into the schedule (break_min long).",
    )
    aggregates: AggregateSpec | None = Field(
        default_factory=AggregateSpec, description="null = trusted totals unavailable."
    )
    as_of: TimeSpec | None = Field(
        default=None, description="Evaluation time; default next day 12:00 local."
    )


class ExpectedAction(_Spec):
    type: str
    punch_type: PunchType | None = None
    punch_id: str | None = Field(default=None, description="adjust_punch: the recorded punch.")
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    day: int = 0
    tolerance_min: int = 15


class Expected(_Spec):
    # eligible: a correct, validated proposal is expected.
    # not_eligible: the case must end escalated or blocked.
    # safe: either is acceptable, but nothing matching forbidden_times may become eligible.
    outcome: Literal["eligible", "not_eligible", "safe"]
    actions: list[ExpectedAction] = Field(default_factory=list)
    clause_ids: list[str] = Field(default_factory=list, description="Acceptable cited clauses.")
    forbidden_times: list[str] = Field(default_factory=list)
    forbidden_action_types: list[str] = Field(default_factory=list)
    status: Literal["blocked", "escalated"] | None = Field(
        default=None,
        description="For not_eligible: the exact status required (blocked = a rule is broken; "
        "escalated = not enough evidence to decide).",
    )


class EvalCase(_Spec):
    id: str
    category: Literal["clear", "ambiguous", "adversarial", "jurisdiction", "evidence", "adjustment"]
    description: str
    rules_only: bool = Field(
        default=False,
        description=(
            "Only real attendance rules can judge this case (breaks, totals). The stand-in "
            "validator is not scored on it."
        ),
    )
    input: InputSpec
    expected: Expected


def at(tz: timezone, hhmm: str, day: int = 0) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(WORK_DATE.year, WORK_DATE.month, WORK_DATE.day, h, m, tzinfo=tz) + timedelta(
        days=day
    )


def build_case_context(case: EvalCase) -> CaseContext:
    spec = case.input
    tz_name, tz = JURISDICTIONS[spec.jurisdiction]
    emp_id = f"E-{case.id}"
    punches = [
        PunchRecord(
            punch_id=f"P-{i}",
            employee_id=emp_id,
            ts=at(tz, p.time, p.day),
            type=p.type,
            source=PunchSource.KIOSK,
        )
        for i, p in enumerate(spec.punches, start=1)
    ]
    if spec.observed_break and spec.schedule is not None and spec.schedule.break_min > 0:
        break_start = at(tz, spec.schedule.start) + timedelta(hours=4)
        for suffix, ts, kind in (
            ("bs", break_start, PunchType.BREAK_START),
            ("be", break_start + timedelta(minutes=spec.schedule.break_min), PunchType.BREAK_END),
        ):
            punches.append(
                PunchRecord(
                    punch_id=f"P-{suffix}",
                    employee_id=emp_id,
                    ts=ts,
                    type=kind,
                    source=PunchSource.KIOSK,
                )
            )
    history = []
    for n in spec.history_days_ago:
        start, end = (
            ("09:00", "18:00")
            if spec.schedule is None
            else (spec.schedule.start, spec.schedule.end)
        )
        end_day = 0 if spec.schedule is None else spec.schedule.end_day
        history += [
            PunchRecord(
                punch_id=f"H-{n}-in",
                employee_id=emp_id,
                ts=at(tz, start, -n),
                type=PunchType.IN,
                source=PunchSource.KIOSK,
            ),
            PunchRecord(
                punch_id=f"H-{n}-out",
                employee_id=emp_id,
                ts=at(tz, end, end_day - n),
                type=PunchType.OUT,
                source=PunchSource.KIOSK,
            ),
        ]
    schedule = (
        ScheduledShift(
            shift_id=f"S-{case.id}",
            employee_id=emp_id,
            start=at(tz, spec.schedule.start),
            end=at(tz, spec.schedule.end, spec.schedule.end_day),
            planned_break_min=spec.schedule.break_min,
        )
        if spec.schedule
        else None
    )
    work = [p for p in punches if p.type in (PunchType.IN, PunchType.OUT)]
    unmatched = work[-1].punch_id if work else None
    as_of = spec.as_of or TimeSpec(time="12:00", day=1)
    return CaseContext(
        exception_id=f"X-{case.id}",
        code=spec.code,
        severity=DEFAULT_SEVERITY[spec.code],
        employee=EmployeeContext(
            employee_id=emp_id,
            location_id=f"LOC-{spec.jurisdiction}",
            jurisdiction=spec.jurisdiction,
            timezone=tz_name,
        ),
        work_date=WORK_DATE,
        rule_version="eval-cases@1",
        punches=punches,
        punch_history=history,
        schedule=schedule,
        notes=[
            EmployeeNote(note_id=f"N-{i}", text=t, submitted_at=at(tz, "21:00"))
            for i, t in enumerate(spec.notes, start=1)
        ],
        detection_details=(
            {"unmatched_punch_id": unmatched}
            if spec.code == ExceptionCode.MISSING_PUNCH
            else {"reason": case.description}  # what Track A's detection writes today
        ),
        evidence_version=f"eval-{case.id}",
        as_of=at(tz, as_of.time, as_of.day),
    )


def expected_ts(case: EvalCase, action: ExpectedAction) -> datetime:
    return at(JURISDICTIONS[case.input.jurisdiction][1], action.time, action.day)


def load_cases(directory: Path = CASES_DIR) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for path in sorted(directory.glob("*.json")):
        cases += [EvalCase.model_validate(c) for c in json.loads(path.read_text("utf-8"))]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate eval case ids")
    return cases
