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

## Active incremental work

| ID | Owner | Status | Scope |
| --- | --- | --- | --- |
| A-START-01 | C V Jayanth | REVIEW | Draft attendance DTOs, deterministic pairing, missing-punch checks; review before shared API adoption |

| A-INTEGRATE-01 | C V Jayanth | REVIEW | Track B case adapter, evidence hash, repository boundary and assigned-manager authorization |

| A-RULES-02 | C V Jayanth | REVIEW | Six deterministic checks and shared action simulation; incomplete aggregate evidence blocks eligibility |

| A-READ-API-01 | C V Jayanth | REVIEW | Demo authenticated exception reads, persisted assignment filtering and repeatable startup |

| A-RULES-03 | C V Jayanth | REVIEW | Aggregate-aware real validator via existing CorrectionValidator interface; work-date scoping; pipeline integration tests (depends on A-RULES-02) |

| A-RULES-04 | C V Jayanth | REVIEW | Agreed Track B answers: per-run totals reload, recorded totals/period/as-of, internal pass/violation/insufficient_evidence outcomes (depends on A-RULES-03; field wiring waits for contract 0.2.0) |

| A-RULES-05 | C V Jayanth | REVIEW | Contract 0.2.0 adopted: RuleCheck.outcome, evidence_ref tolerance, as_of, policy week/quarter (depends on Track B 1c4e895) |

| A-03-DEMO | C V Jayanth | REVIEW | Decision/correction/audit API and trusted day-totals loader on the demo SQLite store; final schema remains A-01/DB-02 |
