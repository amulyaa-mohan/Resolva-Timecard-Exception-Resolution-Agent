"""Provision a synthetic demo week on PostgreSQL that raises all six exception types.

Run from the repository root:
    .venv/bin/python backend/scripts/seed_demo_week.py "postgresql://user@host:5432/resolva"

It uses the real path: it writes employees and assignments, then imports shifts and punches
through the import preview and commit, then runs detection. Nothing is hand-placed in the
exceptions table. Synthetic data only; never point it at a real database.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import secrets
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.attendance.importer import (
    local_dates,
    preview_notes,
    preview_punches,
    preview_shifts,
    read_rows,
)
from app.attendance.ingest import commit_import, import_notes, new_batch_id, run_detection
from app.attendance.postgres import PostgresBackend, apply_migrations
from app.core.config import BACKEND_DIR
from app.policies.registry import PolicyRegistry
from app.resolution.totals import quarter_bounds, upsert_day_total, week_start


def private_json(path: Path, payload) -> None:
    """Owner-only file, created exclusively (same helper as seed_attendance_demo.py)."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")


MANAGER = "M-DEMO-1"
TIMEZONE = "Asia/Kolkata"
EMPLOYEES = {"E-DEMO-1": TIMEZONE, "E-DEMO-2": TIMEZONE, "E-DEMO-3": TIMEZONE}
ORGANIZATION = ("ORG-DEMO", "Resolva Demo Operations")
LOCATION = ("BLR-DEMO", "ORG-DEMO", "Bengaluru Development Centre", "Bengaluru", "India")
# Display only: no rule, validator or authorization check reads these. Synthetic people.
PEOPLE = {
    "E-DEMO-1": ("Aarav Sharma", "Support Associate", "hourly"),
    "E-DEMO-2": ("Diya Nair", "Warehouse Operator", "hourly"),
    "E-DEMO-3": ("Rohan Gupta", "Support Associate", "hourly"),
}

# (employee, weekday offset from Monday, shift start/end, punches, what it demonstrates)
PLAN = [
    (
        "E-DEMO-1",
        0,
        ("09:00", "18:00"),
        [("in", "09:00"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "18:00")],
        "clean day, no exception",
    ),
    (
        "E-DEMO-1",
        1,
        ("09:00", "18:00"),
        [("in", "09:00"), ("break_start", "13:00"), ("break_end", "14:00")],
        "MISSING_PUNCH: no clock-out",
    ),
    (
        "E-DEMO-1",
        2,
        ("09:00", "18:00"),
        [("in", "09:00"), ("out", "18:00")],
        "MEAL_BREAK_BREACH: no break recorded in a 9 h day",
    ),
    (
        # A day whose punches cannot be paired leaves that employee's week unknown, so the
        # overlap case gets its own employee and the other cases stay independently decidable.
        "E-DEMO-3",
        3,
        ("09:00", "18:00"),
        [("in", "09:00"), ("in", "10:00"), ("out", "17:00"), ("out", "18:00")],
        "OVERLAPPING_SHIFT: two open sessions",
    ),
    (
        "E-DEMO-1",
        4,
        ("09:00", "18:00"),
        [("in", "09:25"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "18:00")],
        "SCHEDULE_DEVIATION: 25 min late, tolerance is 7",
    ),
    (
        "E-DEMO-2",
        2,
        ("06:00", "18:30"),
        [
            ("in", "06:00"),
            ("break_start", "10:30"),
            ("break_end", "11:30"),
            ("break_start", "15:00"),
            ("break_end", "16:00"),
            ("out", "18:30"),
        ],
        "SPREAD_OVER_BREACH + OVERTIME_RISK: 12.5 h spread, 10.5 h worked",
    ),
]


# What employees wrote about their own days: (employee, weekday offset, local time submitted, text).
# These give the model something real to cite. Each states a time, because a correction to a
# recorded punch is only accepted when it is backed by a time the employee stated.
NOTES = [
    ("E-DEMO-1", 1, "19:10", "I left at 6:00 pm on Tuesday but forgot to punch out."),
    (
        "E-DEMO-1",
        4,
        "19:30",
        "The kiosk was down when I arrived, I actually got in at 9:05 and started work then.",
    ),
    (
        "E-DEMO-2",
        2,
        "19:00",
        "I was at the gate at 6:00 but only started at 6:30 when it opened. I finished at 6:30 pm.",
    ),
    ("E-DEMO-3", 3, "18:45", "I tapped in twice by mistake. My real shift was 9:00 to 6:00 pm."),
]


def build_notes_csv(monday: date) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["employee_id", "submitted_at", "text"])
    for employee, offset, clock, text in NOTES:
        day = (monday + timedelta(days=offset)).isoformat()
        writer.writerow([employee, f"{day} {clock}", text])
    return out.getvalue()


def demo_week(today: date) -> date:
    """Last week: every day is finished, so detection has final evidence for all of it."""
    return week_start(today) - timedelta(days=7)


def build_csv(monday: date) -> tuple[str, str]:
    shifts = ["employee_id,shift_id,start,end,planned_break_min"]
    punches = ["employee_id,timestamp,type,source_event_id"]
    for employee, offset, (start, end), events, _ in PLAN:
        day = (monday + timedelta(days=offset)).isoformat()
        shifts.append(f"{employee},S-{employee}-{day},{day} {start},{day} {end},60")
        for index, (kind, clock) in enumerate(events):
            punches.append(f"{employee},{day} {clock},{kind},demo-{employee}-{day}-{index}")
    return "\n".join(shifts) + "\n", "\n".join(punches) + "\n"


def seed_history(backend: PostgresBackend, today: date, monday: date) -> int:
    """Trusted prior totals from the quarter start, so weekly and quarterly limits are decidable.

    Without these the overtime rule is correctly 'insufficient evidence' rather than a
    violation: one week of punches cannot establish a quarter. A real deployment gets these
    from its own payroll history; here they are synthetic 8 h weekdays.
    """
    quarter_start, _ = quarter_bounds(monday)
    now = datetime.now(UTC)
    written = 0
    with backend.transaction() as c:
        for employee in EMPLOYEES:
            day = quarter_start
            while day < today:
                weekday = day.weekday() < 5
                upsert_day_total(
                    c,
                    employee_id=employee,
                    work_date=day,
                    worked_hours=8.0 if weekday else 0.0,
                    scheduled_hours=8.0 if weekday else 0.0,
                    complete=True,
                    source="synthetic-demo-history",
                    now=now,
                )
                written += 1
                day += timedelta(days=1)
    return written


def write_credentials(directory: Path) -> Path | None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials, token_path = (
        directory / "manager-credentials.json",
        directory / "manager-token.json",
    )
    if credentials.exists() or token_path.exists():
        return None
    token = secrets.token_urlsafe(32)
    private_json(
        credentials,
        [
            {
                "manager_id": MANAGER,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
                "timezone": TIMEZONE,
            }
        ],
    )
    private_json(token_path, {"access_token": token, "token_type": "bearer"})
    return token_path


def seed(dsn: str, directory: Path) -> None:
    apply_migrations(dsn)
    backend = PostgresBackend(dsn)
    with backend.transaction() as c:
        c.execute("INSERT INTO managers VALUES (?, ?) ON CONFLICT DO NOTHING", (MANAGER, TIMEZONE))
        c.execute(
            "INSERT INTO organizations (org_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING",
            ORGANIZATION,
        )
        c.execute(
            "INSERT INTO locations (location_id, org_id, name, city, country, timezone) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (*LOCATION, TIMEZONE),
        )
        for employee, zone in EMPLOYEES.items():
            name, job, pay_type = PEOPLE[employee]
            c.execute(
                "INSERT INTO employees (employee_id, location_id, jurisdiction, timezone, "
                "full_name, job_title, pay_type) VALUES (?, ?, 'IN-KA', ?, ?, ?, ?) "
                "ON CONFLICT (employee_id) DO UPDATE SET full_name = excluded.full_name, "
                "job_title = excluded.job_title, pay_type = excluded.pay_type",
                (employee, LOCATION[0], zone, name, job, pay_type),
            )
            c.execute(
                "INSERT INTO manager_assignments (manager_id, employee_id, valid_from) "
                "SELECT ?, ?, now() - interval '1 day' WHERE NOT EXISTS (SELECT 1 FROM "
                "manager_assignments WHERE manager_id = ? AND employee_id = ?)",
                (MANAGER, employee, MANAGER, employee),
            )
    today = datetime.now(UTC).astimezone(ZoneInfo(TIMEZONE)).date()
    monday = demo_week(today)
    history = seed_history(backend, today, monday)  # before detection, which overwrites the week
    shifts_csv, punches_csv = build_csv(monday)
    shifts = preview_shifts(read_rows(shifts_csv, "csv"), employee_timezones=EMPLOYEES)
    punches = preview_punches(read_rows(punches_csv, "csv"), employee_timezones=EMPLOYEES)
    if shifts.invalid or punches.invalid:
        bad = [r.error for r in (*shifts.rows, *punches.rows) if r.status == "invalid"]
        raise ValueError(f"demo data is invalid: {bad}")
    added = commit_import(backend, shifts, batch_id=new_batch_id(), manager_id=MANAGER)
    added += commit_import(backend, punches, batch_id=new_batch_id(), manager_id=MANAGER)
    touched = local_dates(punches, EMPLOYEES)
    registry = PolicyRegistry.from_directory(BACKEND_DIR / "policies")
    created = run_detection(backend, registry, touched, as_of=datetime.now(UTC))
    # Notes arrive after detection, as they do in practice: importing them attaches them.
    notes = preview_notes(read_rows(build_notes_csv(monday), "csv"), employee_timezones=EMPLOYEES)
    if notes.invalid:
        raise ValueError(f"demo notes are invalid: {[r.error for r in notes.rows if r.error]}")
    note_count, attached = import_notes(backend, notes, as_of=datetime.now(UTC), manager_id=MANAGER)
    token_path = write_credentials(directory)
    print(
        f"Demo week of {monday.isoformat()}: {added} new records imported, "
        f"{history} synthetic history totals."
    )
    print(f"Exceptions detected ({len(created)}):")
    for exception_id in created:
        print(f"  {exception_id}")
    if created:
        print("\nWhat each day demonstrates:")
        for employee, offset, _, _, note in PLAN:
            print(f"  {employee} {(monday + timedelta(days=offset)).isoformat()}: {note}")
    print(f"Employee notes: {note_count} imported, attached to {len(attached)} exception(s).")
    if token_path:
        print(f"\nManager {MANAGER} credential written to {token_path} (expires in 24 h).")
    else:
        print(f"\nManager credential already present in {directory}; reusing it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dsn", help="PostgreSQL connection string")
    parser.add_argument(
        "--directory", type=Path, default=Path(__file__).resolve().parents[1] / "local"
    )
    arguments = parser.parse_args()
    seed(arguments.dsn, arguments.directory)
