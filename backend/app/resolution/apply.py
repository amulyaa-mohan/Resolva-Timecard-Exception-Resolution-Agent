"""The one definition of "raw punches plus approved corrections".

Three places need the effective timecard: the timecard view, the approval path (which records
the corrected day's hours) and detection (which must not re-raise a fixed exception). They used to
each apply corrections their own way, and each handled a different subset of action types, so
approving an adjust_punch crashed. Everything goes through this function now.

Raw punches are never modified: this returns new records.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from app.core.contracts import PunchRecord, PunchSource

CORRECTION_PREFIX = "correction:"


def _timestamp(action: Mapping[str, Any]) -> datetime | None:
    value = action.get("new_ts")
    if value is None:
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def apply_corrections(
    punches: Iterable[PunchRecord],
    employee_id: str,
    corrections: Iterable[tuple[str, Iterable[Mapping[str, Any]]]],
) -> list[PunchRecord]:
    """Apply (correction_id, actions) pairs, in order, to a copy of the punches.

    - add_punch creates a punch with id ``correction:<correction_id>:<index>``.
    - adjust_punch moves the targeted punch to the new time and changes nothing else; a target
      that is not among these punches is ignored rather than invented.
    - every other action type changes no punch (a premium flag or an acknowledgement is not a
      timecard edit).
    """
    effective = {p.punch_id: p for p in punches}
    for correction_id, actions in corrections:
        for index, action in enumerate(actions):
            ts = _timestamp(action)
            kind = action.get("type")
            if kind == "add_punch" and ts is not None and action.get("punch_type"):
                key = f"{CORRECTION_PREFIX}{correction_id}:{index}"
                effective[key] = PunchRecord(
                    punch_id=key,
                    employee_id=employee_id,
                    ts=ts,
                    type=action["punch_type"],
                    source=PunchSource.IMPORT,
                )
            elif kind == "adjust_punch" and ts is not None:
                target = effective.get(action.get("punch_id"))
                if target is not None:
                    effective[target.punch_id] = target.model_copy(update={"ts": ts})
    return sorted(effective.values(), key=lambda p: p.ts)
