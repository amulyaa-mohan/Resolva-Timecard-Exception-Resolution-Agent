# Database tasks

Claim an owner before starting. Statuses: TODO, IN PROGRESS, BLOCKED, REVIEW, DONE.
Shared dependencies refer to backend/docs/shared/TASKS.md; do not duplicate their status here.

| ID | Task | Owner | Status | Depends on | Acceptance |
| --- | --- | --- | --- | --- | --- |
| DB-01 | Entity design and migration tooling agreement | C V Jayanth | REVIEW | SHARED-01 | ER_DESIGN.md + psycopg/plain-SQL migrations; review with Soumya and Amulya pending |
| DB-02 | Initial schema and migrations | C V Jayanth | REVIEW | DB-01 | 0001_initial.sql: fresh install, re-run no-op, edited-migration refusal and constraints verified on PostgreSQL 15 |
| DB-03 | Reproducible synthetic seeds | Unassigned | TODO | DB-02 | Idempotent synthetic seed run |
| DB-04 | Correction/audit integrity | Unassigned | TODO | DB-02, A-03 | Atomicity, immutability and concurrency checks |
| DB-05 | Migration handoff documentation | C V Jayanth | REVIEW | DB-03, DB-04 | docs/operations.md: install, upgrade, backup/restore, verify, retention, never-do list |
| DB-03 | Reference data and display fields | C V Jayanth | REVIEW | DB-02 | Migration 0003 applied; display-only columns verified not to affect rules |
| DB-06 | Reconcile the database branch (48b2a1a) | C V Jayanth | REVIEW | DB-02 | Done on `database`: docs rewritten for the PostgreSQL schema, SQLite/SQLModel code replaced, her commit kept in history |
| DB-04 | Correction/audit integrity checks | C V Jayanth | REVIEW | DB-02, A-03 | db_maintenance.py verify: audit chain, status mirror, cross-employee evidence, resolved-without-correction; retention split verified |
