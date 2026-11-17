# Backend task ownership

Use backend/docs/shared/TASKS.md as the authoritative status source for existing A-*, B-* and SHARED-* tasks.
This index avoids contradictory copies of task status. Update the shared row when claiming or finishing one.

| Track | Owner | Tasks | Scope |
| --- | --- | --- | --- |
| A | C V Jayanth | A-01 through A-06 | Attendance, rules, validator, decisions, audit; database liaison |
| B | Amulya Mohan | B-01 through B-05 | Policies, retrieval, providers, intents, configuration and CI |
| Shared | Both | SHARED-01 through SHARED-03 | Contracts, integration and delivery |

A-01 coordinates DB-01/DB-02/DB-03 in backend/database/docs/TASKS.md; do not implement a second migration history.
B-01 and B-02 are in REVIEW (mock provider, packaging, policy pack, proposal pipeline). Real providers are B-03.
Record new backend-only tasks below; use a unique ID, owner, status, dependencies and acceptance check.
