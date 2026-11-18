# Resolva Database Operations Runbook

PostgreSQL 15+. Every command is run from the repository root. `$DSN` is the connection string;
keep it out of the shell history and out of Git if it carries a password.

## 1. First install

```bash
pip install -e "./backend[postgres]"
createdb resolva
.venv/bin/python backend/scripts/migrate_postgres.py "$DSN"
```

Then set `ATTENDANCE_ENABLED=true` and `ATTENDANCE_DATABASE_URL` in `backend/.env`.
Startup fails loudly if attendance is enabled without a reachable, migrated database.

## 2. Upgrading an existing database

```bash
.venv/bin/python backend/scripts/migrate_postgres.py "$DSN"
```

Applies only the files not yet in `schema_migrations`, each in its own transaction. Running it
twice applies nothing the second time. It refuses to run a migration whose text changed after it
was applied, because other deployments already ran the old text: add a new migration instead.

**Order of operations for a release:** back up, migrate, then deploy the application. Every
migration so far is additive, so the previous application version keeps working against the new
schema; that is what makes this order safe.

## 3. Backup and restore

```bash
pg_dump --format=custom --file="resolva-$(date +%F).dump" "$DSN"          # back up
pg_restore --clean --if-exists --dbname="$DSN" resolva-2026-11-18.dump    # restore
```

Back up **before every migration**. There are no down migrations: recovery from a bad migration is
restore-then-roll-forward, never a hand-written reverse script. After a restore, run the integrity
check in section 4 before letting managers approve anything.

## 4. Integrity check

```bash
.venv/bin/python backend/scripts/db_maintenance.py verify "$DSN"
```

Exits 1 if it finds a problem, so it can run as a scheduled job. It reports what constraints cannot:

| Finding | Meaning | What to do |
| --- | --- | --- |
| `audit_chain` | an audit event was changed, removed or reordered outside the application | treat as an incident: the ledger is no longer trustworthy from that point |
| `status_mirror` | `exceptions.status` disagrees with the derived status | a write path changed status without going through the store |
| `correction_without_approval` | a correction is attached to a decision that is not an approval | investigate before trusting the corrected timecard |
| `cross_employee_evidence` | an exception cites another employee's punch or note | the detection that wrote it was wrong; re-run detection for that date |
| `resolved_without_correction` | an exception was marked resolved with no correction | a status change that bypassed the decision path |
| `unknown_site` (notice) | employees reference a `location_id` with no `locations` row | backfill the site; nothing is broken |
| `incomplete_days` (notice) | finished days with unknown hours | an unresolved missing punch or overlap; weekly limits stay undecidable until it is fixed |

## 5. Model-text retention

`llm_traces` keeps which model and prompt ran. The model's **raw text** is in `llm_raw_outputs`,
which is deliberately not append-only so it can be purged. A trace survives the purge, so a past
decision stays provable.

```bash
.venv/bin/python backend/scripts/db_maintenance.py purge-traces "$DSN" --older-than-days 30
.venv/bin/python backend/scripts/db_maintenance.py purge-traces "$DSN" --older-than-days 30 --apply
```

Without `--apply` it only reports the count. Agree the window with Track B before scheduling it;
30 days is a placeholder, not a policy.

## 6. What must never be done

| Never | Why |
| --- | --- |
| `UPDATE` or `DELETE` on punches, decisions, corrections, audit_events, proposals, llm_traces | they are the record of what happened; triggers reject it, and disabling a trigger breaks the audit chain |
| Edit a migration that has already been applied | other deployments ran the old text; the runner refuses it |
| Point the seed or test scripts at a shared database | the test fixture drops and recreates the `public` schema |
| Restore a dump over a live database without a backup first | `pg_restore --clean` drops existing objects |
| Store a naive timestamp | local work dates are derived per employee timezone; a naive value silently shifts them |

## 7. Routine checks

| Cadence | Command |
| --- | --- |
| After every migration or restore | `db_maintenance.py verify` |
| Daily (scheduled) | `db_maintenance.py verify`; alert on exit code 1 |
| Monthly | `db_maintenance.py purge-traces --apply`, once the window is agreed |
| Before a demo | `migrate_postgres.py`, then `seed_demo_week.py` against a throwaway database |
