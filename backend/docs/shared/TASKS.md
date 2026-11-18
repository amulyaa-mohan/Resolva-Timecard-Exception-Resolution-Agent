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
| SHARED-01 | Freeze initial API/data contracts | Both | REVIEW | COORD-01 | `0.2.0-draft` (2026-11-18) implements Track A's answers and Amulya's reply: rule outcomes, evidence refs, policy week/quarter/tolerance, as_of (TRACK_B_INTEGRATION.md 5a). Adopted by Track A in 8ad2e15 and verified by Track B's evals (exact outcomes per gap case, live Qwen); freeze pending both owners' sign-off |
| A-01 | DB foundation, synthetic seed, role dependencies | Jayanth | IN PROGRESS | SHARED-01 | Reproducible employee/shift/punch fixture and server-side permission checks |
| B-01 | App configuration, mock provider, development packaging | Amulya | REVIEW | SHARED-01 (draft) | Verified: clean install, server, offline mock, kill-switch, Docker healthy; startup in LOCAL_DEVELOPMENT.md |
| A-02 | Missing-punch detection and correction validation | Jayanth | REVIEW | A-01 (built on the demo store; final schema pending) | Verified: valid fix with trusted totals passes; unsupported, unproven or after-as_of fixes blocked; missing evidence escalates |
| B-02 | One versioned policy pack and proposal pipeline | Amulya | REVIEW | B-01, SHARED-01 (draft) | IN-KA@2025.1 pack; generate_proposal returns eligible/blocked/escalated; real validator pending A-02 |
| A-03 | Decisions, immutable corrections, audit | Jayanth | REVIEW | A-02 (built on the demo SQLite store ahead of A-01) | Verified: atomic decision+correction+audit, stale 409, one approval, idempotent replay, append-only hash-chained audit; see RESOLUTION_API.md |
| SHARED-02 | First end-to-end missing-punch integration | Both | REVIEW | A-03, B-02 | Track A test passes the full path on PostgreSQL (test_import_flow_pg.py); Amulya to review and add PostgreSQL to CI |
| A-04 | Remaining five exception rules | Jayanth | REVIEW | SHARED-01 0.2.0-draft | Six checks with outcomes, totals, policy calendar, as_of; add_punch + adjust_punch validated; acknowledge/add_break/void_shift/flag_premium await agreed semantics |
| B-03 | Hybrid retrieval, real provider, evidence gates | Amulya | REVIEW | SHARED-02 (built early against draft contracts and stub validator) | Verified: wrong-version clauses never retrieved and citations blocked; timeout budget enforced; Ollama live check 6/6; Groq tested with mocked HTTP only |
| A-05 | CSV/JSON import preview and deduplication | Jayanth | REVIEW | A-04, PostgreSQL store | Verified: CSV/JSON equivalence, mapping, DST refusal, dedupe/no-op re-import, scope; import triggers detection (IMPORT_DETECTION.md) |
| B-04 | Multilingual intents and AI fallback | Amulya | REVIEW | B-03 | Verified: 14 commands x en/hi/kn parity 100% with AI off (CI gate) and over live HTTP; write requests refused in all languages; LLM fallback 10/12 on paraphrases with Qwen in two runs, misses failed safe |
| A-06 | Bulk decisions and attendance event updates | Jayanth | IN PROGRESS | A-05 | Bulk decisions verified (per-item auth, validation, stale, idempotency); attendance event updates pending |
| B-05 | CI and reproducible AI evaluation | Amulya | REVIEW | B-04 (done first; eval needs no language work) | CI runs lint, tests, offline eval gates and frontend build; live Qwen reports in backend/evals/reports (prompt v1 vs v2). Evals now use Track A's real validator with complete evidence (break, totals, as_of) plus 9 evidence-gap cases; stand-in shown side by side |
| SHARED-03 | Final integration, startup verification, README | Both | TODO | A-06, B-05 | Fresh setup and full workflow verified; real results documented |

## Decisions pending

- Backend ownership recorded: Track A C V Jayanth, Track B Amulya Mohan.
- Branch migration complete: `main` is default and `cv-jayanth` is removed.
- Final schemas, policy fixtures, and action-specific validation semantics.
- Model provider for the first live demonstration.
- Contract 0.2.0 agreed in substance (2026-11-18; see TRACK_A_CONTRACT_RESPONSE.md, A-RULES-03 answers): RuleCheck.outcome, ProposedAction.evidence_ref, CaseContext.as_of, and the policy fields week_start, quarter_start_month and evidence_tolerance_min. Amulya proposed she authors contracts.py and the pipeline in one commit; Jayanth has not confirmed yet.

## Current next step

Contract `0.2.0-draft` is adopted by both tracks, and the evals use Track A's real validator with complete evidence and exact outcomes (2026-11-18). Next: freeze SHARED-01 (drop -draft, make `as_of` required, update frontend `contracts.ts`), then SHARED-02.
