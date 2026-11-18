# Database updates

Append entries; preserve other developers' history. Use repository-relative paths.

## Entry template

### YYYY-MM-DD — Developer — Task ID — Summary

- Branch and status:
- Changed files and behavior:
- Contracts and cross-team dependencies:
- Validation: actual commands and outcomes; state what was not tested.
- Blockers and next step:
- Publication: local only / branch and commit / PR.

## Updates

### 2026-11-17 — C V Jayanth — COORD-04 — Area agent guidance

- Branch and status: backend; REVIEW (shared documentation preparation).
- Changed: added database area discovery pointer, detailed rules, task tracker and update log.
- Contracts: no business contracts finalized; read docs/CONTRACTS.md before integration.
- Validation: documentation paths and whitespace checked; no application behavior changed.
- Next step: teammates claim tasks and agree shared contracts.
- Publication: local only; these files are not yet available in remote clones.

### 2026-11-17 — C V Jayanth — COORD-05 — Two-folder repository layout

- Branch: main; status REVIEW.
- Changed: consolidated database, policies, prompts, fixtures, evaluations and scripts under backend; shared guides now backend/docs/shared. Frontend remains self-contained. Root keeps README, agent routing and Git ignore rules.
- Configuration: backend/.env.example and backend/.env are now the backend configuration paths, resolved independently of launch directory.
- Validation: backend smoke test passed (one upstream deprecation warning); Ruff passed; TypeScript/Vite build passed; active instruction paths and whitespace checked.
- History: earlier update entries retain their original paths as historical records.
- Next step: teammates bring the main reorganization into their working branches before new work.
- Publication: user authorized direct commit and push to main; team branches are not changed by this operation.

### 2026-11-18 — C V Jayanth — A-INTEGRATE-01 — Persistence boundary for database review

- Added a disposable demo/test SQLite snapshot adapter in backend/app/attendance/repository.py, outside the final migration system and not wired into API startup.
- CaseRepository requires an authorized, consistent case+correction-revision read. The final database adapter must preserve that contract and increment revision atomically on corrections.
- Final normalized tables, migrations and authentication remain unimplemented; no database-owned implementation files were changed.
- Verification: integration suite covers reopen, idempotent seeding, overwrite rejection and employee-manager scope; combined suite 63 passed.
- Next step: review TRACK_A_CONTRACT_RESPONSE.md decisions 3, 7 and 8 before implementing production schema.
- Publication: local only.

### 2026-11-18 — C V Jayanth — A-READ-API-01 — Demo persistence exposed through authorized reads

- Existing disposable DemoCaseRepository now supplies manager-scoped lists as well as details, using stored assignment joins.
- No final schema/migration files changed. Provisioning creates synthetic snapshots and private credential files in ignored backend/local or an explicitly supplied directory.
- Combined suite: 244 passing tests; includes invalid/expired credentials, assignment isolation, hidden unauthorized records and filtering.
- Final normalized attendance/aggregate source and correction/audit transactions remain database integration tasks.
- Publication: local only.

### 2026-11-18 — C V Jayanth — DB-01/DB-02 — PostgreSQL schema and migrations

- Branch: backend; status REVIEW; local only until committed. The team chose PostgreSQL.
  Built by Track A because the database work was not yet pushed. Reconcile with Soumya's work when it arrives.
- Files: database/migrations/0001_initial.sql, database/schema/ER_DESIGN.md, app/attendance/postgres.py
  (migration runner, case repository, decision backend), scripts/migrate_postgres.py.
  The seed script gains `--database-url`.
- Tooling: psycopg 3 as the optional extra `postgres`; plain numbered SQL migrations with checksums. No ORM.
- Verified on a disposable local PostgreSQL 15 (`*_test` database):
  - fresh migrate, then a no-op re-run; an edited applied migration is refused;
  - FK, CHECK and unique constraints; append-only triggers including TRUNCATE;
  - seed idempotency and conflict refusal; an ended assignment removes access;
  - a 4-thread approval race gives exactly 1 winner with an intact audit chain;
  - the full decision API suite passes on both SQLite and PostgreSQL (417 passed with TEST_DATABASE_URL).
- Rollback: forward-only; no destructive down migrations.
- Not done: Docker/CI PostgreSQL service (Track B owns these files); proposals/llm_traces tables; production identity.

### 2026-11-18 — C V Jayanth — DB-03 — Reference data, display fields and review of the database branch

- Branch: backend; status REVIEW; local until committed.
- Migration `0003_organization_and_display_fields.sql`: `organizations`, `locations`, and
  `employees.full_name` / `job_title` / `pay_type`. Display only: no rule, validator or
  authorization check reads them, and detection is verified to work with all of them null.
  No foreign key from `employees.location_id` yet, because existing rows predate `locations`.
- Reviewed `origin/database` 48b2a1a (Soumya). Not merged, and nothing imports it, so nothing is
  broken today. Blocking issues: based on the pre-reorganisation layout, so its files land in a root
  `database/` that duplicates `backend/database/`; SQLite-only DDL (AUTOINCREMENT, PRAGMA, DATETIME)
  while the team chose PostgreSQL; requires `sqlmodel`/`sqlalchemy`, which the project does not
  depend on; naive timestamps; zero immutability triggers despite the specification; cascade deletes
  on exceptions, proposals and shifts. Contract mismatches: integer surrogate keys with no business
  id, wrong severity and punch-source values, no `source_event_id` for import dedupe, no
  `evidence_version`, no decisions table, no day totals, no manager assignment validity.
- Taken from that branch: this migration's reference tables and the documentation set, which is
  better than ours and should be adapted into `backend/database/docs/`.
- Validation: 491 passed with TEST_DATABASE_URL on PostgreSQL 15; fresh migrate 0001-0003 and the
  demo seed verified; the exception list now shows employee names.
- Next step: agree the reconciliation with Soumya, then give her DB-04 (integrity checks) and
  retention for `llm_traces.raw_outputs` against this schema.

### 2026-11-18 — C V Jayanth — DB-06 — Database branch brought onto the PostgreSQL schema

- Branch: `database`, merged from `backend`. Soumya's 48b2a1a stays in history; Git recognised the
  repository reorganisation and relocated her files from the old root `database/` into
  `backend/database/`, so the branch now has one database area instead of two.
- Kept from her work: the documentation structure and the reference-data idea. `README.md`,
  `docs/architecture.md`, `docs/erd.md`, `docs/data_dictionary.md`,
  `docs/immutability_and_audit.md` and `docs/seed_data_guide.md` keep her sections and were
  rewritten to describe the schema that actually runs. `organizations` and `locations` were already
  adopted in migration 0003.
- Replaced: `001_initial_schema.sql` and `apply_migrations.py` (SQLite) by `0001`-`0003` and
  `backend/scripts/migrate_postgres.py`; the thirteen SQLModel modules in `schema/` by the Pydantic
  contracts, which are now the only model definition; `seeds/*.py` and `seeds/policies/*.yaml` by
  `backend/scripts/seed_demo_week.py` and Track B's YAML packs.
- Reasons, in short: the project runs PostgreSQL and CI enforces it; `sqlmodel` and `sqlalchemy` are
  not dependencies; her timestamps were naive; the immutability specification had no triggers behind
  it; evidence cascade-deleted; and ids, severities, punch sources and the missing `evidence_version`
  did not match the agreed contracts. The full review is in `work/DB_BRANCH_REVIEW.md` (local).
- `docs/AGENTS.md` now records the PostgreSQL and no-ORM decision instead of the old SQLite plan.
- Validation on this branch: fresh migrate 0001-0003 on an empty database (19 tables); demo seed
  raises all six exception types; 491 passed with TEST_DATABASE_URL, 454 passed / 37 skipped
  without PostgreSQL; Ruff lint and format pass; `evals.run --gates ci` 9/9 PASS.
- Next step for whoever owns the database area: DB-04 integrity checks, a retention policy for
  `llm_traces.raw_outputs`, indexes for the exception list, and the `employees.location_id` foreign
  key once sites are backfilled.

### 2026-11-18 — C V Jayanth — DB-04/DB-05 — Query performance, retention, integrity checks and runbook

- Branch: backend (database fast-forwarded to match). Status REVIEW.
- The exception list filtered in Python after rebuilding every case. It now filters, counts,
  orders and paginates in SQL, and loads evidence only for the page (`app/attendance/queries.py`
  holds the one definition of the filter, order and derived status, so both stores agree).
- Migration 0004: indexes for the list (`exceptions_employee_work_date`, `exceptions_list_order`),
  the assignment lookup (`manager_assignments_employee`) and the effective timecard
  (`corrections_employee`); and `llm_raw_outputs`, which carries the model's raw text out of the
  append-only `llm_traces` so a retention job can purge it while the trace stays immutable.
- `backend/scripts/db_maintenance.py`: `verify` reports what constraints cannot (audit chain,
  status mirror drift, corrections without an approval, cross-employee evidence, resolved without a
  correction, unknown sites, incomplete days) and exits 1 on a problem; `purge-traces` reports
  before it deletes unless given `--apply`.
- `employees.location_id` is now documented as deliberately not a foreign key: site codes arrive
  with the employee, and the integrity check reports missing `locations` rows as a notice instead.
- Docs: `docs/operations.md` (install, upgrade, backup and restore, verify, retention, never-do
  list, routine cadence); data dictionary gains the index list and the "deliberately absent"
  section; immutability spec gains the retention boundary.
- Validation: 498 passed with TEST_DATABASE_URL on PostgreSQL 15, 454 passed / 44 skipped without
  it; Ruff lint and format pass; fresh migrate 0001-0004 and both maintenance commands run against
  a seeded database.
- Next step: agree the retention window with Track B (30 days is a placeholder), and schedule
  `verify` daily.
