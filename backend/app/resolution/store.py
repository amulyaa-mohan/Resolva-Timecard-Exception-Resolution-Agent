"""Authorized decisions with stale-evidence checks, immutable corrections and audit (A-03).

Demo SQLite store sharing DemoCaseRepository's database file. Each decision runs in one
BEGIN IMMEDIATE transaction: authorize -> idempotency -> stale check -> fresh totals ->
re-validate -> write decision + correction + audit -> bump revision. Any failure rolls
everything back. Raw punches are never modified; corrections are separate rows.

Correction validity (the validator) and authorization (assigned manager) stay separate:
a passing validation never authorizes, and authorization never skips validation.
"""

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.attendance.context import build_verified_case
from app.attendance.repository import CaseAccessDenied
from app.audit import events as audit
from app.core.contracts import CaseContext, ProposedAction, PunchRecord, PunchSource
from app.policies.registry import PolicyRegistry, PolicyResolutionError
from app.resolution import totals
from app.rules.engine import net_worked_hours
from app.rules.validator import make_validator

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    exception_id TEXT NOT NULL REFERENCES demo_case_snapshots(exception_id),
    manager_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approve', 'reject')),
    source TEXT NOT NULL CHECK (source IN ('ai_proposal', 'manager_edit', 'none')),
    evidence_version TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    decided_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS decisions_one_approval
    ON decisions(exception_id) WHERE decision = 'approve';
CREATE TABLE IF NOT EXISTS corrections (
    correction_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL UNIQUE REFERENCES decisions(decision_id),
    exception_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS corrections_no_update BEFORE UPDATE ON corrections
BEGIN SELECT RAISE(ABORT, 'corrections are append-only'); END;
CREATE TRIGGER IF NOT EXISTS corrections_no_delete BEFORE DELETE ON corrections
BEGIN SELECT RAISE(ABORT, 'corrections are append-only'); END;
"""


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    actions: list[ProposedAction] = Field(default_factory=list, max_length=5)
    source: Literal["ai_proposal", "manager_edit"] = "ai_proposal"
    evidence_version: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _shape(self):
        if self.decision == "approve" and not self.actions:
            raise ValueError("approve requires the actions being approved")
        if self.decision == "reject" and self.actions:
            raise ValueError("reject carries no actions")
        if (self.decision == "reject" or self.source == "manager_edit") and not self.reason.strip():
            raise ValueError("a reason is required to reject or to edit a proposal")
        return self


class DecisionResult(BaseModel):
    decision_id: str
    exception_id: str
    decision: Literal["approve", "reject"]
    status: Literal["open", "resolved"]
    evidence_version: str = Field(description="The version the decision was made against.")
    current_evidence_version: str = Field(description="Version after the decision.")
    rule_version: str | None
    policy: str
    audit_event_id: str
    replayed: bool = False


class StaleEvidence(Exception):
    def __init__(self, current: str):
        super().__init__("evidence changed since the proposal was generated")
        self.current = current


class DecisionConflict(Exception):
    """Already approved, or an idempotency key reused with a different request."""


class ValidationRejected(Exception):
    def __init__(self, checks: list[dict]):
        super().__init__("proposed correction fails deterministic validation")
        self.checks = checks


class SqliteBackend:
    """Demo SQLite file shared with DemoCaseRepository (tests and offline demo)."""

    def __init__(self, path: Path):
        self.path = path
        # executescript manages its own transaction; requires DemoCaseRepository tables first.
        connection = sqlite3.connect(path)
        try:
            connection.executescript(audit.SCHEMA + totals.SCHEMA + SCHEMA)
        finally:
            connection.close()

    @contextmanager
    def transaction(self, *, immediate: bool = True):
        # BEGIN IMMEDIATE takes the write lock up front, serializing concurrent decisions.
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
        finally:
            connection.close()

    def load_case(self, connection, exception_id: str, manager_id: str, *, lock: bool):
        row = connection.execute(
            "SELECT c.evidence_json, c.correction_revision FROM demo_case_snapshots c "
            "JOIN demo_employee_managers m ON m.employee_id=c.employee_id "
            "WHERE c.exception_id=? AND m.manager_id=?",
            (exception_id, manager_id),
        ).fetchone()
        if row is None:
            raise CaseAccessDenied("case unavailable for this manager")
        return CaseContext.model_validate_json(row[0]), row[1]

    def mark_resolved(self, connection, exception_id: str, old: int, new: int) -> None:
        updated = connection.execute(
            "UPDATE demo_case_snapshots SET correction_revision=? "
            "WHERE exception_id=? AND correction_revision=?",
            (new, exception_id, old),
        ).rowcount
        if updated != 1:
            raise DecisionConflict("evidence revision changed during the decision")


class ResolutionStore:
    """Decision logic shared by every backend. A backend supplies transactions (with `?`
    placeholders), authorized case loading (row-locked when asked) and the revision bump."""

    def __init__(
        self,
        backend,
        registry: PolicyRegistry,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.backend = SqliteBackend(backend) if isinstance(backend, Path) else backend
        self.registry, self.clock = registry, clock

    def _transaction(self, *, immediate: bool = True):
        return self.backend.transaction(immediate=immediate)

    # ---------------------------------------------------------------- reads

    def _load(
        self, connection, exception_id: str, manager_id: str, *, lock: bool = False
    ) -> tuple[CaseContext, int]:
        case, revision = self.backend.load_case(connection, exception_id, manager_id, lock=lock)
        case = build_verified_case(case, correction_revision=revision)
        return case.model_copy(update={"as_of": self.clock().astimezone(UTC)}), revision

    def resolved_ids(self, exception_ids: list[str]) -> set[str]:
        if not exception_ids:
            return set()
        with self._transaction(immediate=False) as connection:
            marks = ",".join("?" * len(exception_ids))
            rows = connection.execute(
                f"SELECT exception_id FROM decisions WHERE decision='approve' "
                f"AND exception_id IN ({marks})",
                exception_ids,
            ).fetchall()
        return {r[0] for r in rows}

    def audit_trail(self, exception_id: str, manager_id: str) -> list[dict]:
        with self._transaction(immediate=False) as connection:
            self._load(connection, exception_id, manager_id)  # authorization first
            return audit.events_for_exception(connection, exception_id)

    def seed_day_total(self, **fields) -> None:
        """Trusted provisioning only; not exposed over HTTP."""
        with self._transaction() as connection:
            totals.upsert_day_total(connection, now=self.clock(), **fields)

    # ---------------------------------------------------------------- decide

    def decide(
        self, exception_id: str, manager_id: str, request: DecisionRequest
    ) -> DecisionResult:
        now = self.clock()
        request_hash = hashlib.sha256(
            json.dumps(
                [exception_id, manager_id, request.model_dump(mode="json")], sort_keys=True
            ).encode()
        ).hexdigest()
        blocked: ValidationRejected | None = None
        with self._transaction() as connection:
            case, revision = self._load(connection, exception_id, manager_id, lock=True)
            prior = connection.execute(
                "SELECT request_hash, response_json FROM decisions WHERE idempotency_key=?",
                (request.idempotency_key,),
            ).fetchone()
            if prior:
                if prior[0] != request_hash:
                    raise DecisionConflict("idempotency key reused for a different request")
                stored = prior[1] if isinstance(prior[1], str) else json.dumps(prior[1])
                return DecisionResult.model_validate_json(stored).model_copy(
                    update={"replayed": True}
                )
            if request.evidence_version != case.evidence_version:
                raise StaleEvidence(case.evidence_version)
            if connection.execute(
                "SELECT 1 FROM decisions WHERE exception_id=? AND decision='approve'",
                (exception_id,),
            ).fetchone():
                raise DecisionConflict("exception already resolved")
            try:
                policy = self.registry.resolve(case.employee, case.work_date)
            except PolicyResolutionError as exc:
                raise ValidationRejected(
                    [{"code": "POLICY", "passed": False, "reason": str(exc)}]
                ) from exc
            policy_ref = f"{policy.pack_id}@{policy.version}"
            decision_id = f"DEC-{uuid.uuid4().hex}"
            base = {
                "evidence_version": case.evidence_version,
                "policy": policy_ref,
                "reason": request.reason,
            }
            if request.decision == "reject":
                event = audit.append_event(
                    connection,
                    actor_type="manager",
                    actor_id=manager_id,
                    event_type="DECISION_REJECTED",
                    exception_id=exception_id,
                    decision_id=decision_id,
                    payload=base,
                    occurred_at=now,
                )
                result = DecisionResult(
                    decision_id=decision_id,
                    exception_id=exception_id,
                    decision="reject",
                    status="open",
                    evidence_version=case.evidence_version,
                    current_evidence_version=case.evidence_version,
                    rule_version=None,
                    policy=policy_ref,
                    audit_event_id=event,
                )
                self._insert_decision(
                    connection, result, manager_id, "none", request, request_hash, now
                )
                return result

            # Fresh totals at approval time, read inside this transaction (agreed with B).
            used: list = []

            def loader(c):
                used.append(totals.load_aggregates(connection, c, policy, now))
                return used[-1]

            validation = make_validator(loader)(case, list(request.actions), policy)
            aggregates = used[-1] if used else None
            totals_record = (
                None
                if aggregates is None
                else {
                    "week_start": aggregates.week_start.isoformat(),
                    "week_other_worked_hours": aggregates.week_other_worked_hours,
                    "week_remaining_scheduled_hours": aggregates.week_remaining_scheduled_hours,
                    "quarter_start": aggregates.quarter_start.isoformat(),
                    "quarter_other_overtime_hours": aggregates.quarter_other_overtime_hours,
                    "as_of": aggregates.as_of.isoformat(),
                }
            )
            checks = [c.model_dump(mode="json") for c in validation.checks]
            actions = [a.model_dump(mode="json") for a in request.actions]
            if not validation.passed:
                audit.append_event(
                    connection,
                    actor_type="system",
                    actor_id="validator",
                    event_type="APPROVAL_BLOCKED",
                    exception_id=exception_id,
                    payload={
                        **base,
                        "requested_by": manager_id,
                        "actions": actions,
                        "checks": checks,
                        "rule_version": validation.rule_version,
                        "totals": totals_record,
                    },
                    occurred_at=now,
                )
                blocked = ValidationRejected(checks)
            else:
                new_revision = revision + 1
                after = build_verified_case(case, correction_revision=new_revision)
                corrected = [
                    *case.punches,
                    *(
                        PunchRecord(
                            punch_id=f"correction-{i}",
                            employee_id=case.employee.employee_id,
                            ts=a.new_ts,
                            type=a.punch_type,
                            source=PunchSource.IMPORT,
                        )
                        for i, a in enumerate(request.actions)
                    ),
                ]
                event = audit.append_event(
                    connection,
                    actor_type="manager",
                    actor_id=manager_id,
                    event_type="DECISION_APPROVED",
                    exception_id=exception_id,
                    decision_id=decision_id,
                    payload={
                        **base,
                        "source": request.source,
                        "actions": actions,
                        "checks": checks,
                        "rule_version": validation.rule_version,
                        "totals": totals_record,
                        "evidence_version_after": after.evidence_version,
                    },
                    occurred_at=now,
                )
                result = DecisionResult(
                    decision_id=decision_id,
                    exception_id=exception_id,
                    decision="approve",
                    status="resolved",
                    evidence_version=case.evidence_version,
                    current_evidence_version=after.evidence_version,
                    rule_version=validation.rule_version,
                    policy=policy_ref,
                    audit_event_id=event,
                )
                self._insert_decision(
                    connection, result, manager_id, request.source, request, request_hash, now
                )
                connection.execute(
                    "INSERT INTO corrections VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        f"COR-{uuid.uuid4().hex}",
                        decision_id,
                        exception_id,
                        case.employee.employee_id,
                        json.dumps(actions, sort_keys=True),
                        now.astimezone(UTC).isoformat(),
                    ),
                )
                # Raw evidence_json is untouched; the revision makes older proposals stale.
                self.backend.mark_resolved(connection, exception_id, revision, new_revision)
                # Later days' weekly totals must see the corrected hours.
                worked = net_worked_hours(corrected)
                if worked is not None and case.schedule is not None:
                    totals.upsert_day_total(
                        connection,
                        employee_id=case.employee.employee_id,
                        work_date=case.work_date,
                        worked_hours=worked,
                        scheduled_hours=(case.schedule.end - case.schedule.start).total_seconds()
                        / 3600,
                        complete=True,
                        source=f"correction:{decision_id}",
                        now=now,
                    )
                return result
        # The APPROVAL_BLOCKED audit event is committed before the rejection is reported.
        raise blocked

    @staticmethod
    def _insert_decision(connection, result, manager_id, source, request, request_hash, now):
        connection.execute(
            "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result.decision_id,
                result.exception_id,
                manager_id,
                result.decision,
                source,
                result.evidence_version,
                request.idempotency_key,
                request_hash,
                result.model_dump_json(),
                now.astimezone(UTC).isoformat(),
            ),
        )
