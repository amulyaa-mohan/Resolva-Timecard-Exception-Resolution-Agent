# Resolva Database Migrations

Ordered PostgreSQL DDL for the **Resolva — Timecard Exception Resolution Agent**.

## Migration files

| Migration | Adds |
|---|---|
| `0001_initial.sql` | People and access, raw attendance, exceptions and their evidence, decisions, corrections, the audit ledger, day totals, and the append-only triggers |
| `0002_proposals_escalations.sql` | `proposals`, `llm_traces`, `escalations`; allows manager `escalate` decisions |
| `0003_organization_and_display_fields.sql` | `organizations`, `locations`, and employee `full_name` / `job_title` / `pay_type` |
| `0004_indexes_and_trace_retention.sql` | Indexes for the exception list and the effective timecard; moves model raw text into `llm_raw_outputs` so it can be purged |

The runner is `backend/scripts/migrate_postgres.py`.

## Applying migrations

```bash
pip install -e "./backend[postgres]"
.venv/bin/python backend/scripts/migrate_postgres.py "postgresql://user@host:5432/resolva"
```

Each file is applied once, inside its own transaction, and recorded in `schema_migrations` with a
SHA-256 checksum. Re-running the command applies nothing. Never point it at a database you do not own.

## Guidelines

1. **Additive and forward-only.** There are no down migrations. Correct a mistake with a new file;
   never drop audit events or punches.
2. **Do not edit an applied migration.** The runner compares checksums and refuses a file that
   changed after it was applied, because other deployments already ran the old text.
3. **Name files `NNNN_description.sql`.** The runner globs four digits, then an underscore.
4. **Keep the invariants enforced in SQL**, not only in the application: foreign keys
   (`ON DELETE RESTRICT` everywhere), CHECK constraints for enumerated values and ranges, partial
   unique indexes for "one live exception" and "one approval", and the `resolva_append_only`
   triggers for every append-only table.
5. **Instants are `timestamptz`.** Local work dates are derived in the employee's timezone. Naive
   timestamps are never stored.
6. **Verify against a disposable database** before sharing a migration:
   `TEST_DATABASE_URL=postgresql://.../resolva_test pytest backend/tests`. The name must end in
   `_test`, because the fixture drops and recreates its `public` schema.
