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

from app.attendance.repository import DemoCaseRepository
from app.core.contracts import CaseContext
from app.rules.engine import RULE_VERSION


def private_json(path: Path, payload):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")


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
                    "punch_id": "P-DEMO-1",
                    "employee_id": "E-DEMO-1",
                    "ts": "2026-11-17T09:00:00+05:30",
                    "type": "in",
                    "source": "import",
                }
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
    DemoCaseRepository(directory / "attendance.sqlite").seed_case(case, manager_id="M-DEMO-1")
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
