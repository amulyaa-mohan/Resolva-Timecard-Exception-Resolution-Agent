## Existing Team Instructions

Read `database/docs/AGENTS.md`, `database/docs/TASKS.md`, and `database/docs/UPDATE.md` before changing this area. Paths are relative to the repository root.

notepad database\AGENTS.md
# Agent Instructions: Resolva Database Layer

This document establishes non-negotiable rules, operational constraints, and database patterns for AI agents (and automated coding assistants) working on the **Resolva** persistence layer.

---

## 1. Prime Directive: Raw Punch Immutability

```
Count(punch) === 398 (Immutable Constant)
```

- **NEVER** issue an SQL `UPDATE` statement against the `punch` table.
- **NEVER** issue an SQL `DELETE` statement against the `punch` table.
- **NEVER** insert synthetic hardware punches into the `punch` table to resolve an anomaly.
- **ALWAYS** record all timecard adjustments, missed punches, and approved hours in the `correction` table.

Any agent action that reduces or modifies rows in the `punch` table is considered a critical security and compliance regression.

---

## 2. Relational Integrity & SQLite Rules

1. **Foreign Key Enforcement**:
   - SQLite disables foreign keys by default. Always verify that connections execute:
     ```python
     conn.execute("PRAGMA foreign_keys = ON;")
     ```
2. **Multi-Thread Connection Configuration**:
   - Because FastAPI dispatches requests across async thread pools, all SQLite engines must be instantiated with:
     ```python
     connect_args={"check_same_thread": False}
     ```
3. **Session Management via Context Managers**:
   - Never leave unclosed database sessions. Always use:
     ```python
     with Session(engine) as session:
         # perform queries or mutations
         session.commit()
     ```
   - In FastAPI routes, inject the database session using `session: SessionDep` from `app.database`.

---

## 3. Manager Approval & Correction Workflow Rules

When handling supervisor approvals (`APPROVE`), the workflow must execute atomically within a single database transaction:
1. Update `proposal.validator_result` and ensure `proposal.confidence` passes the gate threshold ($> 0.70$).
2. Create exactly one `Correction` record referencing `proposal_id` with `reason_code = 'MANAGER_APPROVED_AI_PROPOSAL'`.
3. Update `exception_record.status = 'resolved'`.
4. Create an `AuditEvent` with `action = 'PROPOSAL_APPROVED'`, actor set to the manager ID, before/after JSON state diffs, and a valid `trace_id`.
5. If any step fails, roll back the transaction immediately so no partial state persists.

---

## 4. Guardrails & Prompt Reproducibility

Before any `Proposal` is written to the database:
1. Validate proposed actions against the allowed whitelist:
   - `INSERT_PUNCH`, `ADJUST_PUNCH`, `DISMISS_DUPLICATE`, `FLAG_MEAL_PREMIUM`, `APPROVE_OVERTIME`, `ACKNOWLEDGE_TARDINESS`, `APPROVE_DEPARTURE`, `MANUAL_REVIEW`.
2. Reject any proposal referencing fictitious policy clauses not present in `policy_clause.clause_id` for that employee's `policy_pack_id`.
3. Verify that proposed timestamps fall strictly within the shift boundary buffer $[-3\text{h}, +5\text{h}]$.
4. Compute and store `prompt_hash = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()`.

---

## 5. Seed Script Idempotency

All seeding scripts in `database/seeds/` must be strictly idempotent:
- Check for existing records by unique keys (`code`, `name`, `clause_id`) before inserting.
- Running `python database/seeds/seed.py` multiple times must **never** create duplicate rows or alter the 398 punch baseline.
