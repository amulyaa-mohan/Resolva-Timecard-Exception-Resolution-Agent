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
    ScheduledShift,
)
from app.policies.registry import PolicyRegistry, PolicyResolutionError
from app.resolution import totals
from app.resolution.apply import CORRECTION_PREFIX, apply_corrections
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


def existing_note_ids(backend: PostgresBackend, preview: ImportPreview) -> frozenset[str]:
    ids = [r.note.note_id for r in preview.rows if r.note is not None]
    if not ids:
        return frozenset()
    with backend.transaction(immediate=False) as c:
        marks = ",".join("?" * len(ids))
        return frozenset(
            r[0]
            for r in c.execute(
                f"SELECT note_id FROM employee_notes WHERE note_id IN ({marks})", ids
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


# A note belongs to an exception when its employee submitted it on the exception's work date
# or the day after (local time). A note carries no date of its own, so this window is the whole
# rule. It must be tight: a note about Friday is not evidence for Tuesday's missing punch, and
# attaching it would hand the model a time that has nothing to do with that day. The cost is a
# note written three days late is not attached; the manager still sees it on the employee.
NOTE_WINDOW_DAYS = 2


def attach_notes(c, employee_ids: set[str], *, as_of: datetime) -> dict[str, list[str]]:
    """Link each employee's notes to their open or escalated exceptions. Idempotent.

    Notes are part of an exception's evidence, so a new link changes `evidence_version`, which
    correctly makes any earlier draft stale. Resolved exceptions are never touched. Returns
    exception id -> the note ids newly linked, and audits each change.
    """
    attached: dict[str, list[str]] = {}
    for employee_id in sorted(employee_ids):
        zone = ZoneInfo(
            c.execute(
                "SELECT timezone FROM employees WHERE employee_id = ?", (employee_id,)
            ).fetchone()[0]
        )
        notes = c.execute(
            "SELECT note_id, submitted_at FROM employee_notes WHERE employee_id = ? "
            "ORDER BY submitted_at, note_id",
            (employee_id,),
        ).fetchall()
        exceptions = c.execute(
            "SELECT exception_id, work_date FROM exceptions WHERE employee_id = ? "
            "AND status IN ('open', 'escalated') ORDER BY exception_id",
            (employee_id,),
        ).fetchall()
        for exception_id, work_date in exceptions:
            start = datetime.combine(work_date, time(0), tzinfo=zone)
            end = start + timedelta(days=NOTE_WINDOW_DAYS)
            linked = []
            for note_id, submitted_at in notes:
                if (
                    start <= submitted_at < end
                    and c.execute(
                        "INSERT INTO exception_notes VALUES (?, ?) ON CONFLICT DO NOTHING",
                        (exception_id, note_id),
                    ).rowcount
                ):
                    linked.append(note_id)
            if linked:
                attached[exception_id] = linked
                audit.append_event(
                    c,
                    actor_type="system",
                    actor_id="import",
                    event_type="EVIDENCE_ATTACHED",
                    exception_id=exception_id,
                    payload={"note_ids": linked, "window_days": NOTE_WINDOW_DAYS},
                    occurred_at=as_of,
                )
    return attached


def import_notes(
    backend: PostgresBackend, preview: ImportPreview, *, as_of: datetime
) -> tuple[int, dict[str, list[str]]]:
    """Store valid notes and attach them to exceptions in ONE transaction.

    Atomic on purpose: a retry after a failure must not find a note imported but unattached,
    because a re-import reports it as a duplicate and would never attach it.
    """
    with backend.transaction() as c:
        inserted = 0
        for row in preview.rows:
            if row.status == "valid" and row.note is not None:
                n = row.note
                inserted += c.execute(
                    "INSERT INTO employee_notes (note_id, employee_id, text, submitted_at) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (n.note_id, n.employee_id, n.text, n.submitted_at),
                ).rowcount
        employees = {r.note.employee_id for r in preview.rows if r.note is not None}
        return inserted, attach_notes(c, employees, as_of=as_of)


def run_detection(
    backend: PostgresBackend,
    registry: PolicyRegistry,
    touched: dict[str, set[date]],
    *,
    as_of: datetime,
) -> list[str]:
    """Recompute day totals, then raise exceptions for violations. Returns new exception ids.

    One transaction PER EMPLOYEE, not one for the whole import. Every writer takes the same lock, so
    a single long transaction stalls every approval behind it: measured at about 5 ms per
    employee, a 5,000-row import of one punch each would hold it for roughly 24 s. Per employee,
    the lock is held for milliseconds and approvals interleave. Detection is idempotent and a
    retry re-checks every date it was given, so a failure part-way loses nothing.
    """
    created: list[str] = []
    for employee_id, dates in sorted(touched.items()):
        with backend.transaction() as c:
            created += _detect_employee(c, registry, employee_id, dates, as_of)
            # Notes already on file belong to the exceptions detection has just raised.
            attach_notes(c, {employee_id}, as_of=as_of)
    return created


def _detect_employee(
    c, registry: PolicyRegistry, employee_id: str, dates: set[date], as_of: datetime
) -> list[str]:
    created: list[str] = []
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
            scheduled_hours=(shift.end - shift.start).total_seconds() / 3600 if shift else 0.0,
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
        findings = detect(
            employee, work_date, day, shift, policy, as_of=as_of, aggregates=aggregates
        )
        _clear_resolved(c, employee_id, work_date, {f.code for f in findings}, as_of)
        for finding in violations(findings):
            exception_id = f"EX-{employee_id}-{work_date.isoformat()}-{finding.code.value}"
            details = {**finding.details, "reason": finding.reason}
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
                    Jsonb(details),
                ),
            ).rowcount
            linked = _link_day_punches(c, exception_id, day)
            if new:
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
            elif _reopen(c, exception_id, details, as_of):
                created.append(exception_id)
            elif linked:
                _note_new_evidence(c, exception_id, linked, as_of)
    return created


def _link_day_punches(c, exception_id: str, day: list[PunchRecord]) -> list[str]:
    """Link the day's raw punches as the exception's evidence; returns the newly linked ids."""
    linked = []
    for punch in day:
        if punch.punch_id.startswith(CORRECTION_PREFIX):
            continue
        if c.execute(
            "INSERT INTO exception_punches VALUES (?, ?) ON CONFLICT DO NOTHING",
            (exception_id, punch.punch_id),
        ).rowcount:
            linked.append(punch.punch_id)
    return linked


def _clear_resolved(c, employee_id: str, work_date: date, still_found: set, as_of: datetime):
    """Dismiss open or escalated exceptions whose rule now PASSES for this day.

    A rule that is merely undecided (insufficient evidence) is left alone: not knowing is not the
    same as being fixed. Without this, a punch imported after the exception was raised left a
    phantom the manager could not resolve (the validator says the problem is no longer present).
    Dismissal is recorded, never a delete, and a recurrence reopens it (see _reopen).
    """
    for exception_id, code, status in c.execute(
        "SELECT exception_id, code, status FROM exceptions WHERE employee_id = ? "
        "AND work_date = ? AND status IN ('open', 'escalated')",
        (employee_id, work_date),
    ).fetchall():
        if code in {f.value for f in still_found}:
            continue
        c.execute(
            "UPDATE exceptions SET status = 'dismissed' WHERE exception_id = ?", (exception_id,)
        )
        audit.append_event(
            c,
            actor_type="system",
            actor_id="detection",
            event_type="EXCEPTION_CLEARED",
            exception_id=exception_id,
            payload={"reason": "the rule now passes after new evidence", "was": status},
            occurred_at=as_of,
        )


def _reopen(c, exception_id: str, details: dict, as_of: datetime) -> bool:
    """Bring a dismissed exception back when its problem returns. True if it was reopened."""
    reopened = c.execute(
        "UPDATE exceptions SET status = CASE WHEN EXISTS (SELECT 1 FROM escalations s "
        "WHERE s.exception_id = exceptions.exception_id) THEN 'escalated' ELSE 'open' END, "
        "detection_details = ? WHERE exception_id = ? AND status = 'dismissed'",
        (Jsonb(details), exception_id),
    ).rowcount
    if reopened:
        audit.append_event(
            c,
            actor_type="system",
            actor_id="detection",
            event_type="EXCEPTION_REOPENED",
            exception_id=exception_id,
            payload={"reason": details.get("reason", "the problem returned")},
            occurred_at=as_of,
        )
    return bool(reopened)


def _note_new_evidence(c, exception_id: str, punch_ids: list[str], as_of: datetime) -> None:
    """New punches joined a live exception. That changes its evidence version, so say so."""
    audit.append_event(
        c,
        actor_type="system",
        actor_id="detection",
        event_type="EVIDENCE_ATTACHED",
        exception_id=exception_id,
        payload={"punch_ids": punch_ids},
        occurred_at=as_of,
    )


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
    corrections = [
        (cid, actions if isinstance(actions, list) else json.loads(actions))
        for cid, actions in c.execute(
            "SELECT correction_id, actions_json FROM corrections WHERE employee_id = ? "
            "ORDER BY created_at, correction_id",
            (employee_id,),
        )
    ]
    effective = apply_corrections(punches, employee_id, corrections)
    # A correction's added punch outside this window belongs to another day.
    return [p for p in effective if not p.punch_id.startswith(CORRECTION_PREFIX) or lo <= p.ts < hi]


def new_batch_id() -> str:
    return f"IMP-{uuid.uuid4().hex[:16]}"
