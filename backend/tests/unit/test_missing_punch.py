from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.attendance.contracts import AttendanceCase, Punch
from app.rules.missing_punch import detect_missing_punches, validate_added_punch


def punch(id="in-1", kind="in", ts="2026-11-17T22:00:00+05:30", **overrides):
    return Punch.model_validate(
        dict(
            id=id,
            employee_id="demo-1",
            event_time=ts,
            event_type=kind,
            source="synthetic",
            source_event_id=id,
            **overrides,
        )
    )


def case(punches=None, as_of="2026-11-18T06:30:00+05:30"):
    return AttendanceCase.model_validate(
        {
            "employee": {
                "id": "demo-1",
                "manager_id": "manager-1",
                "location_id": "demo",
                "timezone": "Asia/Kolkata",
            },
            "schedule": {
                "id": "shift-1",
                "employee_id": "demo-1",
                "start": "2026-11-17T22:00:00+05:30",
                "end": "2026-11-18T06:00:00+05:30",
            },
            "punches": [punch()] if punches is None else punches,
            "evidence_version": "fixture-v1",
            "as_of": as_of,
        }
    )


GRACE = timedelta(minutes=30)


def test_grace_boundary():
    assert not detect_missing_punches(case(as_of="2026-11-18T06:29:59+05:30"), closing_grace=GRACE)
    assert detect_missing_punches(case(), closing_grace=GRACE)[0].missing_event_type == "out"


def test_overnight_fix_preserves_raw_records_and_is_not_approval():
    original = case()
    before = original.model_dump_json()
    result = validate_added_punch(
        original,
        punch("out-1", "out", "2026-11-18T06:00:00+05:30"),
        closing_grace=GRACE,
    )
    assert result.missing_punch_check_passed
    assert not result.approval_eligible
    assert original.model_dump_json() == before


def test_reverse_order_and_timezone_equivalence():
    events = [punch("out-1", "out", "2026-11-18T00:30:00Z"), punch()]
    assert not detect_missing_punches(case(events), closing_grace=GRACE)


def test_orphan_out_and_consecutive_in():
    assert (
        detect_missing_punches(case([punch("out", "out")]), closing_grace=GRACE)[
            0
        ].missing_event_type
        == "in"
    )
    findings = detect_missing_punches(
        case([punch(), punch("in-2", ts="2026-11-17T23:00:00+05:30")]),
        closing_grace=GRACE,
    )
    assert len(findings) == 2


def test_absence_is_not_inferred_as_missing_punch():
    assert not detect_missing_punches(case([]), closing_grace=GRACE)


def test_break_events_do_not_pair_work_punches():
    findings = detect_missing_punches(
        case([punch(), punch("break", "break_end", "2026-11-18T02:00:00+05:30")]),
        closing_grace=GRACE,
    )
    assert len(findings) == 1


def test_equal_timestamps_and_negative_grace_rejected():
    with pytest.raises(ValueError, match="equal-time"):
        detect_missing_punches(case([punch(), punch("out", "out")]), closing_grace=GRACE)
    with pytest.raises(ValueError, match="negative"):
        detect_missing_punches(case(), closing_grace=timedelta(seconds=-1))


@pytest.mark.parametrize(
    "mutation",
    [
        {"employee_id": "other"},
        {"event_time": "2026-11-19T06:00:00Z"},
        {"id": "in-1"},
        {"source_event_id": "in-1"},
    ],
)
def test_invalid_correction_context_rejected(mutation):
    candidate = punch("out", "out", "2026-11-18T06:00:00+05:30").model_dump()
    candidate.update(mutation)
    with pytest.raises(ValidationError):
        validate_added_punch(case(), Punch.model_validate(candidate), closing_grace=GRACE)


def test_naive_timestamps_rejected():
    with pytest.raises(ValidationError):
        punch(ts=datetime(2026, 11, 17, 22))
