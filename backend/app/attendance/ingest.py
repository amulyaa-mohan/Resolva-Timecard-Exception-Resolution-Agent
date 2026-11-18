"""Import commit and detection job on PostgreSQL (A-05 + detection).

commit_import writes valid preview rows in one transaction (re-imports are no-ops through
UNIQUE (source, source_event_id)), then detection re-runs for every touched work date.
Detection evaluates the effective timecard: raw punches plus approved add_punch corrections,
so a resolved exception is not raised again. Raw punches are never modified.
"""

import json
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.attendance.importer import ImportPreview
from app.attendance.postgres import PostgresBackend
from app.audit import events as audit
from app.core.contracts import (
    DEFAULT_SEVERITY,
    EmployeeContext,
    PunchRecord,
    PunchSource,
    ScheduledShift,
)
from app.policies.registry import PolicyRegistry, PolicyResolutionError
from app.resolution import totals
from app.rules.detection import detect, group_by_work_date, shift_for, violations
from app.rules.engine import RULE_VERSION, net_worked_hours


def assigned_employees(backend: PostgresBackend, manager_id: str) -> dict[str, str]:
    """Employee id -> timezone for employees currently assigned to the manager."""
    with backend.transaction(immediate=False) as c:
        return dict(
            c.execute(
                "SELECT e.employee_id, e.timezone FROM employees e WHERE EXISTS (SELECT 1 FROM "
                "manager_assignments a WHERE a.employee_id = e.employee_id AND a.manager_id = ? "
                "AND a.valid_from <= now() AND (a.valid_to IS NULL OR a.valid_to > now()))",
                (manager_id,),
            ).fetchall()
        )


def existing_keys(backend: PostgresBackend, preview: ImportPreview) -> frozenset[tuple[str, str]]:
    ids = [r.punch.punch_id for r in preview.rows if r.punch is not None]
    if not ids:
        return frozenset()
    with backend.transaction(immediate=False) as c:
        marks = ",".join("?" * len(ids))
        return frozenset(
            c.execute(
                f"SELECT source, source_event_id FROM punches WHERE punch_id IN ({marks})", ids
            ).fetchall()
        )


def commit_import(backend: PostgresBackend, preview: ImportPreview, *, batch_id: str) -> int:
    """Insert valid rows; returns how many were new. Caller authorized every employee."""
    inserted = 0
    with backend.transaction() as c:
        for row in preview.rows:
            if row.status != "valid":
                continue
            if row.punch is not None:
                p = row.punch
                event_id = row.source_event_id
                inserted += c.execute(
                    "INSERT INTO punches (punch_id, employee_id, ts, type, source, device_id, "
                    "source_event_id, import_batch_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT DO NOTHING",
                    (
                        p.punch_id,
                        p.employee_id,
                        p.ts,
                        p.type.value,
                        p.source.value,
                        p.device_id,
                        event_id,
                        batch_id,
                    ),
                ).rowcount
            elif row.shift is not None:
                s = row.shift
                inserted += c.execute(
                    "INSERT INTO scheduled_shifts VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (s.shift_id, s.employee_id, s.start, s.end, s.planned_break_min),
                ).rowcount
    return inserted


def run_detection(
    backend: PostgresBackend,
    registry: PolicyRegistry,
    touched: dict[str, set[date]],
    *,
    as_of: datetime,
) -> list[str]:
    """Recompute day totals, then raise exceptions for violations. Returns new exception ids."""
    created: list[str] = []
    with backend.transaction() as c:
        for employee_id, dates in sorted(touched.items()):
            row = c.execute(
                "SELECT employee_id, location_id, jurisdiction, timezone, worker_category "
                "FROM employees WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()
            keys = ("employee_id", "location_id", "jurisdiction", "timezone", "worker_category")
            employee = EmployeeContext.model_validate(dict(zip(keys, row, strict=True)))
            zone = ZoneInfo(employee.timezone)
            # Totals cover each touched date's whole policy week, so the loader finds no gaps.
            week_days = set(dates)
            for touched_date in dates:
                try:
                    start_day = registry.resolve(employee, touched_date).rules.week_start.number
                except PolicyResolutionError:
                    continue
                monday = totals.week_start(touched_date, start_day)
                week_days |= {monday + timedelta(days=i) for i in range(7)}
            first, last = min(week_days) - timedelta(days=1), max(week_days) + timedelta(days=2)
            lo = datetime.combine(first, time(0), tzinfo=zone)
            hi = datetime.combine(last, time(0), tzinfo=zone)
            punches = _effective_punches(c, employee_id, lo, hi)
            shifts = [
                ScheduledShift(
                    shift_id=r[0], employee_id=r[1], start=r[2], end=r[3], planned_break_min=r[4]
                )
                for r in c.execute(
                    "SELECT shift_id, employee_id, start_at, end_at, planned_break_min "
                    "FROM scheduled_shifts WHERE employee_id = ? AND start_at >= ? "
                    "AND start_at < ?",
                    (employee_id, lo, hi),
                )
            ]
            groups = group_by_work_date(punches, employee.timezone)
            for work_date in sorted(week_days):
                day = groups.get(work_date, [])
                shift = shift_for(shifts, work_date, employee.timezone)
                worked = net_worked_hours(day) if day else 0.0
                # Final once the shift (or, unscheduled, the local day) is over. Assumption:
                # schedules are imported for every working day, so an unscheduled past day
                # with no punches is a day off (0 h), not missing data.
                day_end = datetime.combine(work_date + timedelta(days=1), time(0), tzinfo=zone)
                ended = (shift.end if shift else day_end) <= as_of
                totals.upsert_day_total(
                    c,
                    employee_id=employee_id,
                    work_date=work_date,
                    worked_hours=worked or 0.0,
                    scheduled_hours=(shift.end - shift.start).total_seconds() / 3600
                    if shift
                    else 0.0,
                    complete=worked is not None and ended,
                    evidence_final=ended,
                    source="detection",
                    now=as_of,
                )
            for work_date in sorted(week_days):
                day = groups.get(work_date, [])
                shift = shift_for(shifts, work_date, employee.timezone)
                if not day:
                    continue  # absence is not one of the six exceptions
                try:
                    policy = registry.resolve(employee, work_date)
                except PolicyResolutionError:
                    continue
                probe = _probe(employee, work_date)
                aggregates = totals.load_aggregates(c, probe, policy, as_of)
                for finding in violations(
                    detect(
                        employee, work_date, day, shift, policy, as_of=as_of, aggregates=aggregates
                    )
                ):
                    exception_id = f"EX-{employee_id}-{work_date.isoformat()}-{finding.code.value}"
                    new = c.execute(
                        "INSERT INTO exceptions (exception_id, employee_id, shift_id, code, "
                        "severity, work_date, rule_version, detection_details) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        (
                            exception_id,
                            employee_id,
                            shift.shift_id if shift else None,
                            finding.code.value,
                            DEFAULT_SEVERITY[finding.code].value,
                            work_date,
                            RULE_VERSION,
                            Jsonb({"reason": finding.reason}),
                        ),
                    ).rowcount
                    if not new:
                        continue
                    for p in day:
                        if not p.punch_id.startswith("correction:"):
                            c.execute(
                                "INSERT INTO exception_punches VALUES (?, ?)",
                                (exception_id, p.punch_id),
                            )
                    audit.append_event(
                        c,
                        actor_type="system",
                        actor_id="detection",
                        event_type="EXCEPTION_DETECTED",
                        exception_id=exception_id,
                        payload={
                            "code": finding.code.value,
                            "reason": finding.reason,
                            "rule_version": RULE_VERSION,
                            "policy": f"{policy.pack_id}@{policy.version}",
                        },
                        occurred_at=as_of,
                    )
                    created.append(exception_id)
    return created


def _probe(employee: EmployeeContext, work_date: date):
    """Minimal context for the totals loader (it reads only employee and work_date)."""
    from types import SimpleNamespace

    return SimpleNamespace(employee=employee, work_date=work_date)


def _effective_punches(c, employee_id: str, lo: datetime, hi: datetime) -> list[PunchRecord]:
    rows = c.execute(
        "SELECT punch_id, employee_id, ts, type, source, device_id FROM punches "
        "WHERE employee_id = ? AND ts >= ? AND ts < ? ORDER BY ts",
        (employee_id, lo, hi),
    ).fetchall()
    keys = ("punch_id", "employee_id", "ts", "type", "source", "device_id")
    punches = [PunchRecord.model_validate(dict(zip(keys, r, strict=True))) for r in rows]
    for correction_id, actions in c.execute(
        "SELECT correction_id, actions_json FROM corrections WHERE employee_id = ?",
        (employee_id,),
    ):
        for i, action in enumerate(actions if isinstance(actions, list) else json.loads(actions)):
            if action.get("type") != "add_punch":
                continue
            ts = datetime.fromisoformat(action["new_ts"])
            if lo <= ts < hi:
                punches.append(
                    PunchRecord(
                        punch_id=f"correction:{correction_id}:{i}",
                        employee_id=employee_id,
                        ts=ts,
                        type=action["punch_type"],
                        source=PunchSource.IMPORT,
                    )
                )
    return punches


def new_batch_id() -> str:
    return f"IMP-{uuid.uuid4().hex[:16]}"
