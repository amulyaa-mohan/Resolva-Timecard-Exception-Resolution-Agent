# Database tasks

Claim an owner before starting. Statuses: TODO, IN PROGRESS, BLOCKED, REVIEW, DONE.
Shared dependencies refer to backend/docs/shared/TASKS.md; do not duplicate their status here.

| ID | Task | Owner | Status | Depends on | Acceptance |
| --- | --- | --- | --- | --- | --- |
| DB-01 | Entity design and migration tooling agreement | Unassigned | TODO | SHARED-01 | Reviewed ER design and backend model ownership |
| DB-02 | Initial schema and migrations | Unassigned | TODO | DB-01 | Fresh/upgrade paths and constraints verified |
| DB-03 | Reproducible synthetic seeds | Unassigned | TODO | DB-02 | Idempotent synthetic seed run |
| DB-04 | Correction/audit integrity | Unassigned | TODO | DB-02, A-03 | Atomicity, immutability and concurrency checks |
| DB-05 | Migration handoff documentation | Unassigned | TODO | DB-03, DB-04 | Actual commands and limitations recorded |
