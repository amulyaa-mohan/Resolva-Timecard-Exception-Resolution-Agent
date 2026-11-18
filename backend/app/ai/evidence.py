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
from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from app.core.contracts import (
    ActionType,
    CaseContext,
    EvidenceKind,
    EvidenceRef,
    ExceptionCode,
    PolicySnapshot,
    ProposedAction,
)

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


def local_zone(case: CaseContext) -> tzinfo:
    """The employee's timezone. Notes and habits are wall-clock times there, whatever offset
    the stored timestamps carry (a database usually returns UTC)."""
    try:
        return ZoneInfo(case.employee.timezone)
    except (ValueError, KeyError, OSError):  # invalid key; Track A validates it upstream
        if case.schedule is not None:
            return case.schedule.start.tzinfo
        return case.punches[0].ts.tzinfo if case.punches else ZoneInfo("UTC")


def _near(ts: datetime, hour: int, minute: int, window: timedelta) -> bool:
    candidate = ts.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return any(abs(candidate + timedelta(days=d) - ts) <= window for d in (-1, 0, 1))


def missing_evidence(case: CaseContext, policy: PolicySnapshot | None = None) -> list[str]:
    """Human-readable list of missing or conflicting evidence; empty means a proposal may be tried."""
    if case.code != ExceptionCode.MISSING_PUNCH:
        return []

    zone = local_zone(case)
    weekday = case.work_date.weekday()
    same_weekday_history = any(
        p.ts.astimezone(zone).weekday() == weekday for p in case.punch_history
    )
    if case.schedule is None and not same_weekday_history:
        return [
            "No scheduled shift for the work date",
            "No punch history for this weekday to infer the missing time",
            "Actual time from the employee or manager",
        ]

    if case.schedule is not None and policy is not None:
        window = timedelta(minutes=policy.rules.missing_punch_window_min)
        anchors = (case.schedule.start.astimezone(zone), case.schedule.end.astimezone(zone))
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
                f"scheduled {anchors[0]:%H:%M}-{anchors[1]:%H:%M}",
                "Manager to confirm the actual time",
            ]
    return []


# Proposed times must be anchored to evidence, not merely inside the policy window. Found in the
# live eval: an injected note ("clock-out four hours after the scheduled end") made Qwen propose
# 18:30 for an 18:00 shift end, the very edge of the 30-minute window, i.e. unearned pay.
# Contract 0.2.0: the tolerance comes from the policy (evidence_tolerance_min) and every anchored
# time carries an EvidenceRef, so Track A's validator can check the same evidence.
DEFAULT_TOLERANCE = timedelta(minutes=5)


def _candidates(case: CaseContext, action: ProposedAction, local: datetime, tol: timedelta):
    """Evidence that supports `action.new_ts`, strongest first."""
    ts = action.new_ts
    found: list[EvidenceRef] = []
    if case.schedule is not None:
        # Schedule: full date and time (a right time on the wrong day is not supported).
        for kind, at in (
            (EvidenceKind.SCHEDULE_START, case.schedule.start),
            (EvidenceKind.SCHEDULE_END, case.schedule.end),
        ):
            if abs(ts - at) <= tol:
                found.append(EvidenceRef(kind=kind, id=case.schedule.shift_id))
    # Notes and history: time of day (a stated time or a habit, not a date).
    for note in case.notes:
        if any(_near(local, h, m, tol) for h, m in note_times(note.text)):
            found.append(EvidenceRef(kind=EvidenceKind.NOTE, id=note.note_id))
    weekday = case.work_date.weekday()
    for p in case.punch_history:
        at = p.ts.astimezone(local.tzinfo)
        if at.weekday() != weekday or p.type != action.punch_type:
            continue
        if _near(local, at.hour, at.minute, tol):
            found.append(EvidenceRef(kind=EvidenceKind.HISTORY_PUNCH, id=p.punch_id))
    return found


def anchor_times(
    case: CaseContext,
    actions: list[ProposedAction],
    tolerance: timedelta = DEFAULT_TOLERANCE,
) -> tuple[list[ProposedAction], list[str]]:
    """Attach an EvidenceRef to every added punch time, or report why it cannot be anchored.

    Returns (actions with evidence_ref set, problems). Problems:
    - the time is after the case's evaluation time (as_of): a punch cannot be added in the future,
      which also stops a closing punch for a shift that is still open;
    - no schedule time, stated note time or same-weekday history punch supports the time;
    - the model supplied an evidence_ref that does not resolve to supporting evidence.
    """
    if case.code != ExceptionCode.MISSING_PUNCH:
        # Not anchored here, so a model-supplied ref is unverified: never pass it on.
        return [_without_ref(a) for a in actions], []
    zone = local_zone(case)
    problems: list[str] = []
    anchored: list[ProposedAction] = []
    for action in actions:
        if action.type != ActionType.ADD_PUNCH or action.new_ts is None:
            anchored.append(_without_ref(action))
            continue
        ts = action.new_ts
        local = ts.astimezone(zone)
        if case.as_of is not None and ts > case.as_of:
            problems.append(
                f"{local:%H:%M} is after the evaluation time {case.as_of.astimezone(local.tzinfo):%H:%M}"
                " (the shift may still be open)"
            )
            anchored.append(action)
            continue
        found = _candidates(case, action, local, tolerance)
        if action.evidence_ref is not None:
            if action.evidence_ref not in found:
                problems.append(
                    f"{local:%H:%M}: cited evidence {action.evidence_ref.kind.value} "
                    f"{action.evidence_ref.id} does not support it"
                )
            anchored.append(action)
        elif found:
            anchored.append(action.model_copy(update={"evidence_ref": found[0]}))
        else:
            problems.append(f"{local:%H:%M} is not supported by the schedule, notes or history")
            anchored.append(action)
    return anchored, problems


def _without_ref(action: ProposedAction) -> ProposedAction:
    if action.evidence_ref is None:
        return action
    return action.model_copy(update={"evidence_ref": None})


def unanchored_times(
    case: CaseContext, actions, tolerance: timedelta = DEFAULT_TOLERANCE
) -> list[str]:
    """Problems only (kept for callers that do not need the anchored actions)."""
    return anchor_times(case, list(actions), tolerance)[1]
