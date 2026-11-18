# Resolva Database Implementation

PostgreSQL 15+. The schema is plain SQL under `migrations/`; the application reads and writes it
through `backend/app/attendance/postgres.py`. There is no ORM: the shared Pydantic contracts in
`backend/app/core/contracts.py` are the single type definition, so a second model layer cannot
drift from them.

Document set adapted from the database branch's structure (48b2a1a) and rewritten for this schema.

## 1. Directory structure

| Path | Contents |
| --- | --- |
| `migrations/` | Ordered `NNNN_name.sql` files, applied once and recorded with a checksum |
| `schema/ER_DESIGN.md` | Entity design, invariants and how each is enforced |
| `docs/` | Architecture, ERD, data dictionary, immutability spec, seed guide, operations runbook |
| `seeds/` | Reserved; the runnable seeds live in `backend/scripts/` |

Day-to-day operations (backup, migrate, verify, retention): `docs/operations.md`.

Related code: `backend/scripts/migrate_postgres.py` (runner), `backend/scripts/db_maintenance.py`
(integrity checks and retention), `backend/scripts/seed_demo_week.py`
(synthetic demo data), `backend/app/resolution/` (decisions, totals), `backend/app/audit/events.py`
(hash-chained ledger).

## 2. Scale

| Item | Count |
| --- | --- |
| Tables | 19 (plus `schema_migrations`) |
| Migrations | 4 |
| Append-only tables | 6: punches, decisions, corrections, audit_events, proposals, llm_traces |
| Enforcement | Foreign keys (all RESTRICT), CHECK constraints, partial unique indexes, triggers |

## 3. Core architectural principles

### 3.1 Raw punch immutability
Punches are hardware and app telemetry. They are never edited or deleted; triggers reject UPDATE,
DELETE and TRUNCATE. A correction is a separate row, and the effective timecard is the raw punches
with approved corrections applied on top.

### 3.2 Append-only, tamper-evident audit
Every audit event carries the previous event's SHA-256 digest. `verify_chain` recomputes the chain,
so an edit made outside the application (by someone who can drop triggers) is still detectable.

### 3.3 Correct time, everywhere
Every instant is `timestamptz`, stored in UTC. Local work dates are derived in the employee's own
timezone, which is recorded on the employee row. Naive timestamps are not accepted anywhere.

### 3.4 One writer at a time for decisions
Each writing transaction takes an advisory lock and locks the exception row, so two managers cannot
approve the same exception and the audit chain stays linear. A four-thread race test proves exactly
one approval survives.

## 4. Quickstart

```bash
pip install -e "./backend[postgres]"
.venv/bin/python backend/scripts/migrate_postgres.py "postgresql://user@host:5432/resolva"
.venv/bin/python backend/scripts/seed_demo_week.py "postgresql://user@host:5432/resolva"
```

Then set `ATTENDANCE_ENABLED=true` and `ATTENDANCE_DATABASE_URL` in `backend/.env`.
Tests: `TEST_DATABASE_URL=postgresql://.../resolva_test pytest backend/tests`. The database name must
end in `_test`, because the fixture drops and recreates its `public` schema.

Re-running the migration runner is a no-op. Editing a migration that has already been applied is
refused: add a new one. There are no down migrations; roll forward and never drop audit or punch data.
