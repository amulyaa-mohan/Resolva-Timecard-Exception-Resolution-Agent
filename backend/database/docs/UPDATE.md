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
