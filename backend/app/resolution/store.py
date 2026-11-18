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

from app.ai.pipeline import generate_proposal
from app.attendance.context import build_verified_case
from app.attendance.repository import CaseAccessDenied
from app.audit import events as audit
from app.core.contracts import (
    CaseContext,
    GateStatus,
    ProposalResult,
    ProposedAction,
)
from app.policies.registry import PolicyRegistry, PolicyResolutionError
from app.resolution import totals
from app.resolution.apply import apply_corrections
from app.rules.engine import net_worked_hours
from app.rules.validator import make_validator

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    exception_id TEXT NOT NULL REFERENCES demo_case_snapshots(exception_id),
    manager_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approve', 'reject', 'escalate')),
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
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    exception_id TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('eligible', 'blocked', 'escalated')),
    evidence_version TEXT NOT NULL,
    policy_pack_id TEXT, policy_version TEXT, rule_version TEXT,
    proposal_json TEXT, validation_json TEXT,
    gate_checks_json TEXT NOT NULL, reasons_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_traces (
    trace_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES proposals(proposal_id),
    provider TEXT NOT NULL, model_id TEXT, prompt_version TEXT NOT NULL, prompt_hash TEXT,
    retrieved_chunk_ids TEXT NOT NULL,
    attempts INTEGER NOT NULL, latency_ms INTEGER NOT NULL, error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_raw_outputs (
    trace_id TEXT PRIMARY KEY REFERENCES llm_traces(trace_id),
    raw_outputs TEXT NOT NULL, parse_errors TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS escalations (
    exception_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('pipeline', 'manager')),
    escalated_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS proposals_no_update BEFORE UPDATE ON proposals
BEGIN SELECT RAISE(ABORT, 'proposals are append-only'); END;
CREATE TRIGGER IF NOT EXISTS proposals_no_delete BEFORE DELETE ON proposals
BEGIN SELECT RAISE(ABORT, 'proposals are append-only'); END;
"""


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject", "escalate"]
    actions: list[ProposedAction] = Field(default_factory=list, max_length=5)
    source: Literal["ai_proposal", "manager_edit"] = "ai_proposal"
    evidence_version: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _shape(self):
        if self.decision == "approve" and not self.actions:
            raise ValueError("approve requires the actions being approved")
        if self.decision != "approve" and self.actions:
            raise ValueError("only an approval carries actions")
        needs_reason = self.decision != "approve" or self.source == "manager_edit"
        if needs_reason and not self.reason.strip():
            raise ValueError("a reason is required to reject, escalate or edit a proposal")
        return self


class DecisionResult(BaseModel):
    decision_id: str
    exception_id: str
    decision: Literal["approve", "reject", "escalate"]
    status: Literal["open", "resolved", "escalated"]
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

    def load_case(
        self, connection, exception_id: str, manager_id: str, *, lock: bool, raw: bool = False
    ):
        row = connection.execute(
            "SELECT c.evidence_json, c.correction_revision FROM demo_case_snapshots c "
            "JOIN demo_employee_managers m ON m.employee_id=c.employee_id "
            "WHERE c.exception_id=? AND m.manager_id=?",
            (exception_id, manager_id),
        ).fetchone()
        if row is None:
            raise CaseAccessDenied("case unavailable for this manager")
        return CaseContext.model_validate_json(row[0]), row[1]

    def effective_workday(self, connection, case: CaseContext):
        # The demo stores only exception snapshots, rather than employee punch history.
        return None

    def still_open(self, connection, exception_id: str) -> bool:
        """The demo store never dismisses an exception, so it is always live here."""
        return True

    def mark_escalated(self, connection, exception_id: str) -> None:
        """The escalations table is the demo store's only status record."""

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

    def statuses(self, exception_ids: list[str]) -> dict[str, str]:
        """exception_id -> open | escalated | resolved (an approval supersedes an escalation)."""
        if not exception_ids:
            return {}
        with self._transaction(immediate=False) as connection:
            marks = ",".join("?" * len(exception_ids))
            approved = {
                r[0]
                for r in connection.execute(
                    f"SELECT exception_id FROM decisions WHERE decision='approve' "
                    f"AND exception_id IN ({marks})",
                    exception_ids,
                )
            }
            escalated = {
                r[0]
                for r in connection.execute(
                    f"SELECT exception_id FROM escalations WHERE exception_id IN ({marks})",
                    exception_ids,
                )
            }
        return {
            i: "resolved" if i in approved else "escalated" if i in escalated else "open"
            for i in exception_ids
        }

    @staticmethod
    def _approved(connection, exception_id: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM decisions WHERE exception_id=? AND decision='approve'",
                (exception_id,),
            ).fetchone()
            is not None
        )

    def _escalate(self, connection, exception_id: str, reason: str, source: str, now) -> None:
        connection.execute(
            "INSERT INTO escalations VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (exception_id, reason[:500], source, now.astimezone(UTC).isoformat()),
        )
        self.backend.mark_escalated(connection, exception_id)

    def effective_timecard(self, exception_id: str, manager_id: str) -> dict:
        """Raw punches plus approved corrections: what the timecard now says (A-06)."""
        with self._transaction(immediate=False) as connection:
            case, _ = self.backend.load_case(
                connection, exception_id, manager_id, lock=False, raw=True
            )
            rows = connection.execute(
                "SELECT c.correction_id, c.actions_json FROM corrections c "
                "JOIN decisions d ON d.decision_id = c.decision_id "
                "WHERE c.exception_id = ? AND d.decision = 'approve' ORDER BY c.created_at",
                (exception_id,),
            ).fetchall()
            effective = self.backend.effective_workday(connection, case)
        parsed = [
            (cid, actions if isinstance(actions, list) else json.loads(actions))
            for cid, actions in rows
        ]
        applied = [
            {"correction_id": cid, **action} for cid, actions in parsed for action in actions
        ]
        if effective is None:
            effective = apply_corrections(case.punches, case.employee.employee_id, parsed)
        return {
            "exception_id": exception_id,
            "employee_id": case.employee.employee_id,
            "work_date": case.work_date,
            "raw_punches": case.punches,
            "corrections_applied": applied,
            "effective_punches": effective,
            "net_worked_hours": net_worked_hours(effective),
        }

    def audit_trail(self, exception_id: str, manager_id: str) -> list[dict]:
        with self._transaction(immediate=False) as connection:
            self._load(connection, exception_id, manager_id)  # authorization first
            return audit.events_for_exception(connection, exception_id)

    def seed_day_total(self, **fields) -> None:
        """Trusted provisioning only; not exposed over HTTP."""
        with self._transaction() as connection:
            totals.upsert_day_total(connection, now=self.clock(), **fields)

    # ---------------------------------------------------------------- propose

    def propose(self, exception_id: str, manager_id: str, *, provider, settings) -> ProposalResult:
        """Draft a correction for an authorized case and persist it with its model trace.

        Track B's generate_proposal runs the gates and calls the real validator with trusted
        totals read in the same snapshot as the case, without holding the write lock (audit
        A2). Nothing here approves: an eligible proposal is only a draft a manager may then
        approve, and approval re-validates against fresh evidence and totals.
        """
        now = self.clock()
        # Audit A2: the model call (up to the LLM budget) used to run inside the write
        # transaction, holding the global write lock, so every proposal, decision and import
        # queued behind it. Now: (1) a short read, (2) the pipeline with no lock held, (3) a
        # short write that re-checks the evidence before persisting.
        with self._transaction(immediate=False) as connection:
            case, revision = self._load(connection, exception_id, manager_id)
            if self._approved(connection, exception_id):
                raise DecisionConflict("exception already resolved")
            # Refuse before any model call: a dismissed case gets no draft (Codex review).
            if not self.backend.still_open(connection, exception_id):
                raise DecisionConflict("exception is no longer open; request a new proposal")
            try:
                policy = self.registry.resolve(case.employee, case.work_date)
            except PolicyResolutionError:
                policy = None  # the pipeline escalates without an applicable policy
            # Trusted totals, read once from the same snapshot as the case.
            aggregates = totals.load_aggregates(connection, case, policy, now) if policy else None

        result = generate_proposal(
            case,
            policy,
            provider=provider,
            validator=make_validator(lambda _case: aggregates),
            settings=settings,
        )

        with self._transaction() as connection:
            current, current_revision = self._load(connection, exception_id, manager_id, lock=True)
            if self._approved(connection, exception_id):
                raise DecisionConflict("exception already resolved")
            if current_revision != revision or current.evidence_version != case.evidence_version:
                raise DecisionConflict(
                    "evidence changed while the proposal was drafted; request a new proposal"
                )
            if not self.backend.still_open(connection, exception_id):
                raise DecisionConflict("exception is no longer open; request a new proposal")
            proposal_id = f"PRP-{uuid.uuid4().hex}"
            connection.execute(
                "INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal_id,
                    exception_id,
                    manager_id,
                    result.status.value,
                    result.evidence_version,
                    result.policy_pack_id,
                    result.policy_version,
                    result.validation.rule_version if result.validation else None,
                    result.proposal.model_dump_json() if result.proposal else None,
                    result.validation.model_dump_json() if result.validation else None,
                    json.dumps([g.model_dump(mode="json") for g in result.gate_checks]),
                    json.dumps(result.reasons),
                    now.astimezone(UTC).isoformat(),
                ),
            )
            trace = result.trace
            # Audit A3: the request trace id comes from the client (X-Trace-Id) and repeats
            # across retries, so it cannot be a primary key on its own.
            trace_key = f"{trace.trace_id}:{proposal_id}"
            # The trace is immutable audit evidence; the model's own text lives in its own
            # table so a retention job can purge it without touching the trace.
            connection.execute(
                "INSERT INTO llm_traces (trace_id, proposal_id, provider, model_id, "
                "prompt_version, prompt_hash, retrieved_chunk_ids, attempts, latency_ms, error, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    trace_key,
                    proposal_id,
                    trace.provider,
                    trace.model_id,
                    trace.prompt_version,
                    trace.prompt_hash,
                    json.dumps(trace.retrieved_chunk_ids),
                    trace.attempts,
                    trace.latency_ms,
                    trace.error,
                    now.astimezone(UTC).isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO llm_raw_outputs VALUES (?, ?, ?, ?)",
                (
                    trace_key,
                    json.dumps(trace.raw_outputs),
                    json.dumps(trace.parse_errors),
                    now.astimezone(UTC).isoformat(),
                ),
            )
            if result.status == GateStatus.ESCALATED:
                self._escalate(
                    connection,
                    exception_id,
                    "; ".join(result.reasons) or "escalated by gates",
                    "pipeline",
                    now,
                )
            audit.append_event(
                connection,
                actor_type="ai",
                actor_id=f"{trace.provider}:{trace.model_id or 'unknown'}",
                event_type="PROPOSAL_GENERATED",
                exception_id=exception_id,
                payload={
                    "proposal_id": proposal_id,
                    "status": result.status.value,
                    "requested_by": manager_id,
                    "evidence_version": result.evidence_version,
                    "policy": f"{result.policy_pack_id}@{result.policy_version}",
                    "prompt_version": trace.prompt_version,
                    "trace_id": trace.trace_id,
                    "trace_key": trace_key,
                    "reasons": result.reasons,
                },
                occurred_at=now,
            )
            return result

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
            if not self.backend.still_open(connection, exception_id):
                raise DecisionConflict("exception is no longer open")
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
            if request.decision in ("reject", "escalate"):
                escalating = request.decision == "escalate"
                if escalating:
                    self._escalate(connection, exception_id, request.reason, "manager", now)
                event = audit.append_event(
                    connection,
                    actor_type="manager",
                    actor_id=manager_id,
                    event_type="DECISION_ESCALATED" if escalating else "DECISION_REJECTED",
                    exception_id=exception_id,
                    decision_id=decision_id,
                    payload=base,
                    occurred_at=now,
                )
                result = DecisionResult(
                    decision_id=decision_id,
                    exception_id=exception_id,
                    decision=request.decision,
                    status="escalated" if escalating else "open",
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
                raw_case, _ = self.backend.load_case(
                    connection, exception_id, manager_id, lock=False, raw=True
                )
                after = build_verified_case(raw_case, correction_revision=new_revision)
                corrected = apply_corrections(
                    case.punches,
                    case.employee.employee_id,
                    [(decision_id, actions)],  # `actions` is the JSON form built above
                )
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
                effective = self.backend.effective_workday(connection, case)
                worked = net_worked_hours(corrected if effective is None else effective)
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
