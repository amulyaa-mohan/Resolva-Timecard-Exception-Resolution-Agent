"""Provision synthetic attendance plus one expiring local manager credential.

Run from root: .venv/bin/python backend/scripts/seed_attendance_demo.py
Credentials are written to permission-restricted ignored files, never stdout.
"""

import argparse
import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.attendance.repository import DemoCaseRepository
from app.core.config import BACKEND_DIR
from app.core.contracts import CaseContext
from app.policies.registry import PolicyRegistry
from app.resolution.store import ResolutionStore
from app.resolution.totals import quarter_bounds, week_start
from app.rules.engine import RULE_VERSION

POLICIES = BACKEND_DIR / "policies"


def private_json(path: Path, payload):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")


def seed_day_totals(store: ResolutionStore, case: CaseContext) -> None:
    """Synthetic trusted history: 8 h weekdays before today, scheduled hours afterwards.

    Days before the employee's local today are complete. Re-run provisioning in a fresh
    directory on a later day, or the loader will (correctly) report incomplete history.
    """
    today = datetime.now(UTC).astimezone(ZoneInfo(case.employee.timezone)).date()
    quarter_start, _ = quarter_bounds(case.work_date)
    day, last = quarter_start, week_start(max(today, case.work_date)) + timedelta(days=6)
    while day <= last:
        weekday = day.weekday() < 5
        done = day < today or day == case.work_date
        store.seed_day_total(
            employee_id=case.employee.employee_id,
            work_date=day,
            worked_hours=8.0 if weekday and done else 0.0,
            scheduled_hours=8.0 if weekday else 0.0,
            complete=done,
            source="synthetic-demo-seed",
        )
        day += timedelta(days=1)


def seed(directory: Path):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials = directory / "manager-credentials.json"
    token_path = directory / "manager-token.json"
    if credentials.exists() or token_path.exists():
        raise ValueError(
            "Credentials already exist. Choose a new directory to provision fresh demo credentials."
        )
    case = CaseContext.model_validate(
        {
            "exception_id": "X-DEMO-1",
            "code": "MISSING_PUNCH",
            "severity": "problem",
            "employee": {
                "employee_id": "E-DEMO-1",
                "location_id": "BLR-DEMO",
                "jurisdiction": "IN-KA",
                "timezone": "Asia/Kolkata",
            },
            "work_date": "2026-11-17",
            "rule_version": RULE_VERSION,
            "punches": [
                {
                    "punch_id": f"P-DEMO-{i}",
                    "employee_id": "E-DEMO-1",
                    "ts": f"2026-11-17T{clock}:00+05:30",
                    "type": kind,
                    "source": "import",
                }
                for i, (kind, clock) in enumerate(
                    [("in", "09:00"), ("break_start", "13:00"), ("break_end", "14:00")], 1
                )
            ],
            "schedule": {
                "shift_id": "S-DEMO-1",
                "employee_id": "E-DEMO-1",
                "start": "2026-11-17T09:00:00+05:30",
                "end": "2026-11-17T18:00:00+05:30",
                "planned_break_min": 60,
            },
            "detection_details": {"unmatched_punch_id": "P-DEMO-1"},
            "evidence_version": "seed-pending",
        }
    )
    database = directory / "attendance.sqlite"
    DemoCaseRepository(database).seed_case(case, manager_id="M-DEMO-1")
    seed_day_totals(ResolutionStore(database, PolicyRegistry.from_directory(POLICIES)), case)
    token = secrets.token_urlsafe(32)
    private_json(
        credentials,
        [
            {
                "manager_id": "M-DEMO-1",
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
                "timezone": "Asia/Kolkata",
            }
        ],
    )
    private_json(token_path, {"access_token": token, "token_type": "bearer"})
    print(f"Synthetic X-DEMO-1 provisioned. Private local token file: {token_path}")
    print("Credential expires in 24 hours. Configure ATTENDANCE_ENABLED=true to enable reads.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=Path(__file__).resolve().parents[1] / "local"
    )
    seed(parser.parse_args().directory)
