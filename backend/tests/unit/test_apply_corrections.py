"""apply_corrections: the one definition of 'raw punches plus approved corrections'."""

from datetime import datetime

import pytest

from app.core.contracts import PunchRecord, PunchSource
from app.resolution.apply import CORRECTION_PREFIX, apply_corrections
from tests.factories import IST


def punch(pid, hour, kind="in"):
    return PunchRecord(
        punch_id=pid,
        employee_id="E-001",
        ts=datetime(2026, 11, 12, hour, 0, tzinfo=IST),
        type=kind,
        source=PunchSource.KIOSK,
    )


RAW = [punch("P-0", 9), punch("P-1", 13, "break_start"), punch("P-2", 14, "break_end")]


def add_out(hour=18):
    return {
        "type": "add_punch",
        "punch_type": "out",
        "new_ts": datetime(2026, 11, 12, hour, 0, tzinfo=IST).isoformat(),
    }


def test_add_punch_creates_a_correction_punch_and_leaves_raw_untouched():
    result = apply_corrections(RAW, "E-001", [("C1", [add_out()])])
    assert [p.punch_id for p in result] == ["P-0", "P-1", "P-2", f"{CORRECTION_PREFIX}C1:0"]
    assert result[-1].type == "out" and result[-1].source == PunchSource.IMPORT
    assert [p.punch_id for p in RAW] == ["P-0", "P-1", "P-2"]  # the input list is not modified


def test_adjust_punch_moves_the_target_and_adds_nothing():
    """The regression: approving an adjust_punch used to crash by building a punch with no type."""
    adjust = {
        "type": "adjust_punch",
        "punch_id": "P-0",
        "new_ts": datetime(2026, 11, 12, 8, 55, tzinfo=IST).isoformat(),
    }
    result = apply_corrections(RAW, "E-001", [("C1", [adjust])])
    assert len(result) == 3
    assert next(p for p in result if p.punch_id == "P-0").ts == datetime(
        2026, 11, 12, 8, 55, tzinfo=IST
    )
    assert RAW[0].ts == datetime(2026, 11, 12, 9, 0, tzinfo=IST)  # raw punch is immutable


@pytest.mark.parametrize(
    "action",
    [
        {"type": "adjust_punch", "punch_id": "P-404", "new_ts": "2026-11-12T08:55:00+05:30"},
        {"type": "acknowledge"},
        {"type": "flag_premium"},
        {"type": "add_punch", "punch_type": "out"},  # no time
        {"type": "add_punch", "new_ts": "2026-11-12T18:00:00+05:30"},  # no punch type
        {"type": "suggest_schedule_swap", "new_ts": "2026-11-12T18:00:00+05:30"},
    ],
)
def test_actions_that_are_not_timecard_edits_change_nothing(action):
    assert apply_corrections(RAW, "E-001", [("C1", [action])]) == sorted(RAW, key=lambda p: p.ts)


def test_corrections_apply_in_order_and_can_move_a_corrected_punch():
    first = add_out(18)
    move_it = {
        "type": "adjust_punch",
        "punch_id": f"{CORRECTION_PREFIX}C1:0",
        "new_ts": datetime(2026, 11, 12, 17, 55, tzinfo=IST).isoformat(),
    }
    result = apply_corrections(RAW, "E-001", [("C1", [first]), ("C2", [move_it])])
    assert result[-1].ts == datetime(2026, 11, 12, 17, 55, tzinfo=IST)
    assert len(result) == 4
