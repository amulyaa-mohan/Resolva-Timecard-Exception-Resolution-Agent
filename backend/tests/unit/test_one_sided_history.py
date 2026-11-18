"""Codex finding 2: a same-weekday habit is one-sided, like a stated time.

A habitual 18:00 clock-out must not support a proposed 18:05 clock-out (that adds paid time
nobody claimed). Moving earlier, which removes paid time, is still allowed.
"""

from datetime import datetime

from app.core.contracts import EvidenceKind, PunchType
from app.rules.validator import _within
from tests.factories import IST

TOLERANCE_SECONDS = 5 * 60
HABIT_OUT = [datetime(2026, 11, 12, 18, 0, tzinfo=IST)]


def test_habit_out_does_not_support_a_later_clock_out():
    assert not _within(
        datetime(2026, 11, 12, 18, 5, tzinfo=IST),
        HABIT_OUT,
        TOLERANCE_SECONDS,
        kind=EvidenceKind.HISTORY_PUNCH,
        punch_type=PunchType.OUT,
    )


def test_habit_out_supports_an_earlier_clock_out_within_tolerance():
    assert _within(
        datetime(2026, 11, 12, 17, 55, tzinfo=IST),
        HABIT_OUT,
        TOLERANCE_SECONDS,
        kind=EvidenceKind.HISTORY_PUNCH,
        punch_type=PunchType.OUT,
    )


def test_habit_in_does_not_support_an_earlier_clock_in_that_adds_pay():
    anchor = [datetime(2026, 11, 12, 9, 0, tzinfo=IST)]
    assert not _within(
        datetime(2026, 11, 12, 8, 55, tzinfo=IST),
        anchor,
        TOLERANCE_SECONDS,
        kind=EvidenceKind.HISTORY_PUNCH,
        punch_type=PunchType.IN,
    )
    assert _within(
        datetime(2026, 11, 12, 9, 5, tzinfo=IST),
        anchor,
        TOLERANCE_SECONDS,
        kind=EvidenceKind.HISTORY_PUNCH,
        punch_type=PunchType.IN,
    )


def test_stated_time_is_still_one_sided_and_schedule_is_still_two_sided():
    late = datetime(2026, 11, 12, 18, 5, tzinfo=IST)
    assert not _within(
        late, HABIT_OUT, TOLERANCE_SECONDS, kind=EvidenceKind.NOTE, punch_type=PunchType.OUT
    )
    assert _within(
        late,
        HABIT_OUT,
        TOLERANCE_SECONDS,
        kind=EvidenceKind.SCHEDULE_END,
        punch_type=PunchType.OUT,
    )
