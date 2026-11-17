# Shared task tracker

Statuses: TODO, IN PROGRESS, BLOCKED, REVIEW, DONE.
Claim a task by updating its owner and status before implementation. Review remote updates first.
DONE means acceptance verified and review completed; REVIEW means ready for teammate review.

| ID | Task | Owner | Status | Depends on | Acceptance / next step |
| --- | --- | --- | --- | --- | --- |
| SCAFFOLD-01 | Workspace and runnable structural scaffold | Jayanth | REVIEW | — | Health test, lint, web build and live proxy checks passed; local review pending |
| COORD-03 | Relocate agent instructions and updates to backend/docs | Jayanth | REVIEW | — | Files moved; root discovery pointer and references updated |
| COORD-04 | Area-specific agent guidance and progress logs | Jayanth | REVIEW | — | Frontend/backend/database guides and routing verified |
| COORD-05 | Simplify to frontend/backend root folders | Jayanth | REVIEW | — | References/config verified; backend test, lint and frontend build passed |
| COORD-01 | Shared instructions and tracker | Jayanth | REVIEW | — | Teammates read rules and record task ownership |
| SHARED-01 | Freeze initial API/data contracts | Both | REVIEW | COORD-01 | Draft `0.1.0-draft` by Amulya in backend/app/core/contracts.py; Jayanth answers the 10 decisions in TRACK_B_INTEGRATION.md section 5, then both freeze |
| A-01 | DB foundation, synthetic seed, role dependencies | Jayanth | TODO | SHARED-01 | Reproducible employee/shift/punch fixture and server-side permission checks |
| B-01 | App configuration, mock provider, development packaging | Amulya | REVIEW | SHARED-01 (draft) | Verified: clean install, server, offline mock, kill-switch, Docker healthy; startup in LOCAL_DEVELOPMENT.md |
| A-02 | Missing-punch detection and correction validation | Jayanth | TODO | A-01 | Missing punch detected; valid fix passes; unsupported fix blocked |
| B-02 | One versioned policy pack and proposal pipeline | Amulya | REVIEW | B-01, SHARED-01 (draft) | IN-KA@2025.1 pack; generate_proposal returns eligible/blocked/escalated; real validator pending A-02 |
| A-03 | Decisions, immutable corrections, audit | Jayanth | TODO | A-02 | Authorized decision creates correction and audit; stale approval rejected |
| SHARED-02 | First end-to-end missing-punch integration | Both | TODO | A-03, B-02 | Ingest → detect → propose → validate → approve → audit passes |
| A-04 | Remaining five exception rules | Jayanth | TODO | SHARED-02 | Boundary, overlap, overnight, and timezone tests pass |
| B-03 | Hybrid retrieval, real provider, evidence gates | Amulya | REVIEW | SHARED-02 (built early against draft contracts and stub validator) | Verified: wrong-version clauses never retrieved and citations blocked; timeout budget enforced; Ollama live check 6/6; Groq tested with mocked HTTP only |
| A-05 | CSV/JSON import preview and deduplication | Jayanth | TODO | A-04 | Equivalent inputs produce equivalent records and rule outcomes |
| B-04 | Multilingual intents and AI fallback | Amulya | TODO | B-03 | English/Kannada/Hindi intent parity; rules-only path verified |
| A-06 | Bulk decisions and attendance event updates | Jayanth | TODO | A-05 | Per-item eligibility, permission, and duplicate-decision checks |
| B-05 | CI and reproducible AI evaluation | Amulya | REVIEW | B-04 (done first; eval needs no language work) | CI runs lint, tests, offline eval gates and frontend build; live Qwen reports in backend/evals/reports (prompt v1 vs v2) |
| SHARED-03 | Final integration, startup verification, README | Both | TODO | A-06, B-05 | Fresh setup and full workflow verified; real results documented |

## Decisions pending

- Backend ownership recorded: Track A C V Jayanth, Track B Amulya Mohan.
- Branch migration complete: `main` is default and `cv-jayanth` is removed.
- Final schemas, policy fixtures, and action-specific validation semantics.
- Model provider for the first live demonstration.

## Current next step

Jayanth reviews the SHARED-01 draft (TRACK_B_INTEGRATION.md section 5, 11 decisions) and builds A-01/A-02 against it; Amulya starts B-04. When A-02 lands, swap the stand-in validator in evals.
