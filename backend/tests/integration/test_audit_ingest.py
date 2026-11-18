"""Audit of the code written after Track B's audit: adjust_punch approval, lifecycle, hostile input."""

from datetime import datetime

import pytest

from app.core.contracts import CaseContext, EmployeeNote, PunchRecord, PunchSource
from tests.factories import IST, make_case
from tests.integration.test_resolution_api import (  # noqa: F401  (fixtures)
    NOW,
    approve_body,
    auth,
    env,
    seed_totals,
    version,
)


def late_arrival_case() -> CaseContext:
    """Warning-severity deviation: clocked in 25 min late; the employee's note says 9:05."""
    data = make_case().model_dump()
    data.update(
        exception_id="X-LATE",
        code="SCHEDULE_DEVIATION",
        severity="warning",
        detection_details={"boundary": "start", "minutes_off": 25},
    )
    data["employee"]["employee_id"] = "E-LATE"
    data["schedule"].update(employee_id="E-LATE", shift_id="S-LATE")
    events = [("in", 9, 25), ("break_start", 13, 0), ("break_end", 14, 0), ("out", 18, 0)]
    data["punches"] = [
        PunchRecord(
            punch_id=f"LATE-P{i}",
            employee_id="E-LATE",
            ts=datetime(2026, 11, 12, h, m, tzinfo=IST),
            type=kind,
            source=PunchSource.KIOSK,
        ).model_dump()
        for i, (kind, h, m) in enumerate(events)
    ]
    data["notes"] = [
        EmployeeNote(
            note_id="N-LATE",
            text="The kiosk was down, I actually got in at 9:05.",
            submitted_at=datetime(2026, 11, 12, 19, 0, tzinfo=IST),
        ).model_dump()
    ]
    return CaseContext.model_validate(data)


@pytest.fixture
def late(env):  # noqa: F811
    client, store, database = env
    from app.attendance.postgres import PostgresCaseRepository
    from app.attendance.repository import DemoCaseRepository

    repo = (
        PostgresCaseRepository(database.target)
        if database.kind == "postgres"
        else DemoCaseRepository(database.target)
    )
    repo.seed_case(late_arrival_case(), manager_id="M-1")
    seed_totals(store, employee="E-LATE")
    return client, store, database


def adjust_body(client, key="adjust-key-0001"):
    return {
        "decision": "approve",
        "source": "manager_edit",
        "reason": "Employee note states the true arrival time.",
        "actions": [
            {
                "type": "adjust_punch",
                "punch_id": "LATE-P0",
                "new_ts": "2026-11-12T09:05:00+05:30",
                "evidence_ref": {"kind": "note", "id": "N-LATE"},
            }
        ],
        "evidence_version": version(client, "X-LATE"),
        "idempotency_key": key,
    }


def test_approving_an_adjust_punch_moves_the_punch_instead_of_adding_one(late):
    client, _, database = late
    response = client.post("/exceptions/X-LATE/decisions", json=adjust_body(client), headers=auth())
    assert response.status_code == 200, response.text
    card = client.get("/exceptions/X-LATE/timecard", headers=auth()).json()
    assert len(card["raw_punches"]) == 4 and len(card["effective_punches"]) == 4
    moved = next(p for p in card["effective_punches"] if p["punch_id"] == "LATE-P0")
    assert moved["ts"].startswith("2026-11-12T09:05")
    assert card["raw_punches"][0]["ts"].startswith("2026-11-12T09:25")  # raw is never rewritten
    # The day's stored hours reflect the moved punch: 09:05-18:00 less a 1 h break.
    worked = database.scalar(
        "SELECT worked_hours FROM day_totals WHERE employee_id='E-LATE' AND work_date=?",
        ("2026-11-12" if database.kind == "sqlite" else __import__("datetime").date(2026, 11, 12),),
    )
    assert abs(worked[0] - (7 + 55 / 60)) < 1e-6
