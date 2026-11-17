# Shared task tracker

Statuses: TODO, IN PROGRESS, BLOCKED, REVIEW, DONE.
Claim a task by updating its owner and status before implementation. Review remote updates first.
DONE means acceptance verified and review completed; REVIEW means ready for teammate review.

| ID | Task | Owner | Status | Depends on | Acceptance / next step |
| --- | --- | --- | --- | --- | --- |
| COORD-01 | Shared instructions and tracker | Jayanth | REVIEW | — | Teammate reads rules, records name, and agrees integration branch |
| SHARED-01 | Freeze initial API/data contracts | Both | TODO | COORD-01 | Agree typed inputs, outputs, errors, and evidence versions |
| A-01 | DB foundation, synthetic seed, role dependencies | Jayanth | TODO | SHARED-01 | Reproducible employee/shift/punch fixture and server-side permission checks |
| B-01 | App configuration, mock provider, development packaging | Teammate | TODO | SHARED-01 | Backend starts; mock provider runs offline; startup documented |
| A-02 | Missing-punch detection and correction validation | Jayanth | TODO | A-01 | Missing punch detected; valid fix passes; unsupported fix blocked |
| B-02 | One versioned policy pack and proposal pipeline | Teammate | TODO | B-01, SHARED-01 | Structured mock proposal or explicit escalation; validator interface wired |
| A-03 | Decisions, immutable corrections, audit | Jayanth | TODO | A-02 | Authorized decision creates correction and audit; stale approval rejected |
| SHARED-02 | First end-to-end missing-punch integration | Both | TODO | A-03, B-02 | Ingest → detect → propose → validate → approve → audit passes |
| A-04 | Remaining five exception rules | Jayanth | TODO | SHARED-02 | Boundary, overlap, overnight, and timezone tests pass |
| B-03 | Hybrid retrieval, real provider, evidence gates | Teammate | TODO | SHARED-02 | Wrong-version clauses and invalid citations blocked; timeout handled |
| A-05 | CSV/JSON import preview and deduplication | Jayanth | TODO | A-04 | Equivalent inputs produce equivalent records and rule outcomes |
| B-04 | Multilingual intents and AI fallback | Teammate | TODO | B-03 | English/Kannada/Hindi intent parity; rules-only path verified |
| A-06 | Bulk decisions and attendance event updates | Jayanth | TODO | A-05 | Per-item eligibility, permission, and duplicate-decision checks |
| B-05 | CI and reproducible AI evaluation | Teammate | TODO | B-04 | CI runs shared tests and reports measured safety/retrieval outcomes |
| SHARED-03 | Final integration, startup verification, README | Both | TODO | A-06, B-05 | Fresh setup and full workflow verified; real results documented |

## Decisions pending

- Teammate's name and personal branch.
- Shared integration branch and review process.
- Final schemas, policy fixtures, and action-specific validation semantics.
- Model provider for the first live demonstration.

## Current next step

Both developers review the coordination files and agree SHARED-01 before application coding.
