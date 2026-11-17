"""Deterministic evidence gate (B-03, extended in B-05), checked BEFORE the model is called.

Design doc section 8 lists cases that must always escalate. When the evidence needed to justify a
fix is absent or contradicted, the model is never asked, so it cannot guess.

- Missing evidence: found in the live Qwen2.5-7B check, where the model invented a clock-out 30
  minutes after clock-in for a case with no schedule; no attendance rule flags such a shift.
- Conflicting evidence: policy allows inferring a punch from the schedule only "when no other
  evidence contradicts it". An employee note that mentions a time outside the inference window
  contradicts the schedule. Notes stay untrusted: a contradiction is a reason for human review,
  never something the system acts on.

Requirements for other exception codes need agreed detection_details keys (SHARED-01 decision 11).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.core.contracts import CaseContext, ExceptionCode, PolicySnapshot

# Clock times such as 21:30, 9:05, 18.05 or 9.45 pm; not part of a longer number, date or version.
_TIME = re.compile(
    r"(?<![\d:])(?<!\d\.)([01]?\d|2[0-3])[:.]([0-5]\d)(?![\d:])(?!\.\d)"
    r"(?:\s*([ap])\.?\s?m\b\.?)?",
    re.IGNORECASE,
)


def note_times(text: str) -> list[tuple[int, int]]:
    times = []
    for h, m, meridiem in _TIME.findall(text):
        hour = int(h)
        if meridiem.lower() == "p" and hour < 12:
            hour += 12
        elif meridiem.lower() == "a" and hour == 12:
            hour = 0
        times.append((hour, int(m)))
    return times


def _near(ts: datetime, hour: int, minute: int, window: timedelta) -> bool:
    candidate = ts.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return any(abs(candidate + timedelta(days=d) - ts) <= window for d in (-1, 0, 1))


def missing_evidence(case: CaseContext, policy: PolicySnapshot | None = None) -> list[str]:
    """Human-readable list of missing or conflicting evidence; empty means a proposal may be tried."""
    if case.code != ExceptionCode.MISSING_PUNCH:
        return []

    weekday = case.work_date.weekday()
    same_weekday_history = any(p.ts.date().weekday() == weekday for p in case.punch_history)
    if case.schedule is None and not same_weekday_history:
        return [
            "No scheduled shift for the work date",
            "No punch history for this weekday to infer the missing time",
            "Actual time from the employee or manager",
        ]

    if case.schedule is not None and policy is not None:
        window = timedelta(minutes=policy.rules.missing_punch_window_min)
        anchors = (case.schedule.start, case.schedule.end)
        conflicts = sorted(
            {
                f"{h:02d}:{m:02d}"
                for note in case.notes
                for h, m in note_times(note.text)
                if not any(_near(a, h, m, window) for a in anchors)
            }
        )
        if conflicts:
            return [
                f"Employee note mentions {', '.join(conflicts)}, which conflicts with the "
                f"scheduled {case.schedule.start:%H:%M}-{case.schedule.end:%H:%M}",
                "Manager to confirm the actual time",
            ]
    return []
