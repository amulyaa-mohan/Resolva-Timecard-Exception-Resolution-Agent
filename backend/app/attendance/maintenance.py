"""Database integrity checks and retention (DB-04).

The checks here deliberately do **not** repeat what a constraint already guarantees. Foreign
keys, CHECK constraints and the partial unique indexes are enforced by PostgreSQL on every
write; re-asserting them would only prove the database works. These look for the things no
constraint can express: the audit hash chain, the denormalised status mirror, cross-row
ownership, and data an operator still needs to fill in.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.attendance.queries import status_expression
from app.audit.events import verify_chain


@dataclass(frozen=True)
class Finding:
    level: str  # "problem" or "notice"
    check: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.check}: {self.detail}"


def _rows(connection, sql: str, params=()) -> list:
    return connection.execute(sql, params).fetchall()


def verify(connection) -> list[Finding]:
    """Every invariant that no constraint can enforce. Empty means the database is sound."""
    findings: list[Finding] = []

    if not verify_chain(connection):
        findings.append(
            Finding(
                "problem",
                "audit_chain",
                "the audit hash chain does not verify: an event was changed, removed or "
                "reordered outside the application",
            )
        )

    # exceptions.status is a mirror of the derived status, kept for operators reading SQL.
    drifted = _rows(
        connection,
        f"SELECT e.exception_id, e.status, {status_expression('e')} FROM exceptions e "
        f"WHERE e.status <> ({status_expression('e')})",
    )
    for exception_id, stored, derived in drifted:
        findings.append(
            Finding(
                "problem",
                "status_mirror",
                f"{exception_id} is stored as {stored} but derives as {derived}",
            )
        )

    # A correction may only exist because a manager approved it.
    for (correction_id,) in _rows(
        connection,
        "SELECT c.correction_id FROM corrections c JOIN decisions d "
        "ON d.decision_id = c.decision_id WHERE d.decision <> 'approve'",
    ):
        findings.append(
            Finding(
                "problem",
                "correction_without_approval",
                f"{correction_id} is attached to a decision that is not an approval",
            )
        )

    # Evidence must belong to the employee whose exception it is. No constraint spans both.
    for exception_id, punch_id in _rows(
        connection,
        "SELECT ep.exception_id, ep.punch_id FROM exception_punches ep "
        "JOIN exceptions e ON e.exception_id = ep.exception_id "
        "JOIN punches p ON p.punch_id = ep.punch_id WHERE p.employee_id <> e.employee_id",
    ):
        findings.append(
            Finding(
                "problem",
                "cross_employee_evidence",
                f"{exception_id} cites punch {punch_id}, which belongs to another employee",
            )
        )
    for exception_id, note_id in _rows(
        connection,
        "SELECT en.exception_id, en.note_id FROM exception_notes en "
        "JOIN exceptions e ON e.exception_id = en.exception_id "
        "JOIN employee_notes n ON n.note_id = en.note_id WHERE n.employee_id <> e.employee_id",
    ):
        findings.append(
            Finding(
                "problem",
                "cross_employee_evidence",
                f"{exception_id} cites note {note_id}, which belongs to another employee",
            )
        )

    # A resolved exception should have been corrected; a bare status change would be a bug.
    for (exception_id,) in _rows(
        connection,
        "SELECT e.exception_id FROM exceptions e WHERE e.status = 'resolved' AND NOT EXISTS "
        "(SELECT 1 FROM corrections c WHERE c.exception_id = e.exception_id)",
    ):
        findings.append(
            Finding(
                "problem",
                "resolved_without_correction",
                f"{exception_id} is resolved but has no correction record",
            )
        )

    # Operator work, not corruption.
    for (location_id,) in _rows(
        connection,
        "SELECT DISTINCT e.location_id FROM employees e WHERE NOT EXISTS "
        "(SELECT 1 FROM locations l WHERE l.location_id = e.location_id)",
    ):
        findings.append(
            Finding(
                "notice",
                "unknown_site",
                f"employees reference site {location_id}, which has no locations row",
            )
        )
    purged = _rows(
        connection,
        "SELECT count(*) FROM llm_traces t WHERE NOT EXISTS "
        "(SELECT 1 FROM llm_raw_outputs r WHERE r.trace_id = t.trace_id)",
    )[0][0]
    if purged:
        findings.append(
            Finding(
                "notice",
                "purged_traces",
                f"{purged} model trace(s) have had their raw text removed by retention",
            )
        )
    incomplete = _rows(
        connection,
        "SELECT count(*) FROM day_totals WHERE NOT complete AND work_date < current_date",
    )[0][0]
    if incomplete:
        findings.append(
            Finding(
                "notice",
                "incomplete_days",
                f"{incomplete} finished day(s) still have unknown hours, so weekly and "
                "quarterly limits cannot be decided for those weeks",
            )
        )
    return findings


def purge_raw_outputs(
    connection,
    *,
    older_than_days: int,
    now: datetime | None = None,
    dry_run: bool = False,
) -> int:
    """Delete model text older than the retention window; returns how many were affected.

    The trace row itself is never touched: provider, model, prompt hash, attempts, latency and
    any error stay, so a past decision remains provable after its raw text is gone.
    `dry_run` counts the same rows without deleting them.
    """
    if older_than_days < 1:
        raise ValueError("retention window must be at least one day")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=older_than_days)
    if dry_run:
        return connection.execute(
            "SELECT count(*) FROM llm_raw_outputs WHERE created_at < ?", (cutoff,)
        ).fetchone()[0]
    return connection.execute(
        "DELETE FROM llm_raw_outputs WHERE created_at < ?", (cutoff,)
    ).rowcount
