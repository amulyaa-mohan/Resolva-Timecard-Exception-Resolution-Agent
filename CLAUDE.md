# CLAUDE.md

Claude Code context for Resolva. Shared team rules live in AGENTS.md (imported below) and the area
guides it routes to; this file adds Claude-specific context and the live Track B state.
**Keep this file current**: update "Current state" and "Next up" at the end of every working session,
in the same commit as the work.

@AGENTS.md

## Who and what

- User: Amulya Mohan (repo owner), backend **Track B: Policy and AI**. Git identity `amulyaa-mohan`.
- Teammate: C V Jayanth, backend **Track A: Attendance and Resolution**. He uses OpenAI Codex, which
  reads AGENTS.md. Anything he must know goes in AGENTS.md-routed docs, not only here.
- Project: Resolva, Dayforce AI Innovation Challenge use case 5 (timecard exception resolution).
  Principle: AI drafts, deterministic rules verify, an authorized manager decides.
- Source docs (untracked, not committed): `Resolva — Timecard Exception Resolution Agent.pdf` (design
  spec), `AI_Innovation_Challenge_University_Brief 1.pdf`, `ShiftSense_Product_Enhancement_Proposal.docx`.

## Track B owns

`backend/app/{policies,retrieval,ai,language}`, `backend/policies/`, `backend/prompts/`, provider
adapters, the evidence gates, app configuration, Docker and CI (`.github/workflows/` at the root).
Shared, coordinate first: `backend/app/core/` (especially `contracts.py`), API contracts, integration tests.
Do not edit Track A modules (`attendance`, `rules`, `resolution`, `audit`) or migrations.

## Where things are tracked

- Task status: `backend/docs/shared/TASKS.md` (authoritative). Progress log: append to `backend/docs/UPDATE.md`.
- Integration guide for Track A / Codex: `backend/docs/shared/TRACK_B_INTEGRATION.md`. Update it whenever
  a Track B interface, file location or contract changes.
- Setup: `backend/docs/shared/LOCAL_DEVELOPMENT.md`.

## Commands (Windows, Git Bash, from repo root)

```bash
venv/Scripts/python.exe -m pip install -r backend/requirements-dev.lock -e './backend[dev]'
venv/Scripts/python.exe -m pytest backend/tests
venv/Scripts/python.exe -m ruff check backend && venv/Scripts/python.exe -m ruff format --check backend
cd backend && ../venv/Scripts/python.exe -m uvicorn app.main:app --reload   # http://localhost:8000/docs
cd backend && docker compose up --build                                    # needs Docker Desktop running
```

The local virtualenv is `venv/` (Jayanth's docs use `.venv/`; both are git-ignored).
Settings are unprefixed env vars or `backend/.env` (`AI_ENABLED`, `LLM_PROVIDER`, `CONFIDENCE_THRESHOLD`, ...).

## Current state (2026-11-18, after Track A sync)

- Branch `backend` (on top of `main` 68ede72). B-01/B-02 3874367, B-03 ef619b6, B-05 2099dc5 +
  c6bde83 (time-evidence gate) + live reports. CI green on GitHub for each push.
- Track A pushed 1c8b820 (attendance context, missing-punch detector, partial `validate_correction`
  in `app/rules/validator.py` that always returns passed=false) and merged PR #6 into `main`.
  His answers: `backend/docs/shared/TRACK_A_CONTRACT_RESPONSE.md`. Amulya replied (2026-11-18):
  totals via `make_validator` (no contract change); `RuleCheck.outcome` pass/violation/
  insufficient_evidence (violation -> BLOCKED, insufficient -> ESCALATED); validator stays
  exact-time until `ProposedAction.evidence_ref` + a pack `evidence_tolerance_min`; evals get
  complete evidence and show stub vs real validator side by side; pack fields `week_start`
  (Monday) and `quarter_start_month` (1); `CaseContext.as_of` (UTC, excluded from
  evidence_version).
- SHARED-01: `0.2.0-draft` implemented by Track B (2026-11-18): `RuleOutcome`, `EvidenceRef`
  attached deterministically by `anchor_times` in `app/ai/evidence.py`, policy
  `evidence_tolerance_min`/`week_start`/`quarter_start_month`, optional `CaseContext.as_of`
  (added punch after it blocks; shown in `<facts>`). Handover in TRACK_B_INTEGRATION.md 5a. His validator must return at least one `RuleCheck` and enforce the
  missing-punch inference window. Frontend type mismatches are listed in backend/docs/shared/CONTRACTS.md.
- B-01 to B-05 all in REVIEW. B-04: `POST /assistant/query` (en/hi/kn -> Intent, read-only); lexicon
  parity is a CI gate; LLM fallback for paraphrases (Qwen 10/12, misses failed safe). The model may
  not add severity/status/employee filters the manager didn't state.
- Pipeline order: kill-switch -> policy applicable -> pre-model evidence gate (`app/ai/evidence.py`: no
  schedule/history, or a note time conflicting with the schedule) -> hybrid retrieval -> model (8 s budget,
  1 repair retry) -> schema -> exception id -> escalation citations stripped if unverified -> allowed
  actions -> time evidence (added punch within 5 min of schedule/stated time/history) -> citations
  retrieved + verbatim -> validator (non-empty) -> missing info -> confidence.
- Prompts: `propose_v3` (default since step 2: stated-time adjustment rules), `propose_v2` (trusted
  `<facts>` block with local dates) and `propose_v1`.
- Step 2 (2026-11-18): proposals for SCHEDULE_DEVIATION, SPREAD_OVER_BREACH, OVERLAPPING_SHIFT via
  adjust_punch to a stated time. Pre-model gate escalates with no usable stated time; stated and
  history times round one way (no extra pay); per-code `<facts>`; mangled-but-unambiguous citation
  ids normalised (`citation_ids_normalised`). Eval category `adjustment` (12 cases, 57 total).
- Evals: `cd backend && python -m evals.run` (45 labelled cases incl. 9 evidence-gap cases, 20 scripted
  unsafe outputs, 12 retrieval cases). Since 2026-11-18 proposals are validated by Track A's
  `make_validator` with trusted eval totals (`evals/aggregates.py`); cases carry an observed break,
  totals and `as_of`; the stand-in judges the same recorded outputs as a comparison column. CI (`.github/workflows/ci.yml`) runs lint, format, pytest, eval gates, frontend build.
  Live reports at c6bde83 (Qwen2.5-7B): v1 83% proposal accuracy, v2 100% (two runs); 0 unsafe
  eligible and 100% injection resistance in all runs. Numbers are in docs/MODEL_CARD.md.
  Real-model results vary run to run; rely on the deterministic gates.
- Latest live report (dcccc0c, real validator, 45 cases): all 6 live gates pass, proposal accuracy
  100% under real and stand-in, every category 100%, p50 4.78 s; real rules made 0/6 rules-only
  cases eligible vs 6/6 for the stand-in. Lexicon intents 100% en/hi/kn, paraphrases 10/12.
- Tests: 590 with `TEST_DATABASE_URL` (PostgreSQL tests skip without it). If Windows Application
  Control blocks the psycopg DLL, run them in `python:3.12-slim` on the compose network (see UPDATE.md). (466 with `TEST_DATABASE_URL`; CI runs them on a
  `postgres:15` service and fails if they skip). `docker compose --profile postgres` for local PG. `tzdata` is a runtime dependency (Windows/slim images). Local Ollama in Docker: `cd backend && docker compose -f docker-compose.yml
  -f docker-compose.gpu.yml --profile ollama up -d ollama` (models persist in the `ollama-models` volume).

## Next up

0. Backend audit 2026-11-18 (`backend/docs/shared/AUDIT_2026-11-18.md`): B1-B3 and, at Amulya's
   request, Track A's A1-A7 fixed by Track B (one-off exception to the ownership split). Jayanth
   to review, especially A5 (schedule deviation = late arrival / early departure only).
1. Jayanth adopted 0.2.0 (8ad2e15) and added PostgreSQL, import/detection, bulk decisions and
   adjust_punch (c85111c). Track B answers to his A-05/A-06 questions are in
   TRACK_A_CONTRACT_RESPONSE.md (adjust_punch gate done; proposals for acknowledge, add_break
   [`new_end_ts`], void_shift [`target_punch_ids`], flag_premium, swap = advisory; one-sided
   rounding of stated times). On agreement: draft contract 0.3.0, make swap proposals ESCALATED,
   then freeze SHARED-01 (drop -draft, `as_of` required, frontend `contracts.ts`).
1b. Step 2 done (uncommitted until Amulya approves): after committing, generate the committed
   live report (prompt v3, 57 cases) from a clean tree and add it to MODEL_CARD.md.
2. SHARED-02 with Jayanth: first end-to-end missing-punch flow through his routes; wire
   `ExceptionQuery` filters into his exception list.
3. Ask native Hindi/Kannada speakers to review the lexicons and reply templates.
4. Optional: intent prompt v2 with few-shot examples to lift paraphrase accuracy (measure first).

## Working agreements for Claude

- Before work: `git fetch`, read new teammate commits, and integrate `main` if it moved. Never overwrite Jayanth's files.
- Mock-provider results prove the harness, not model quality. Never present them as model accuracy.
- Never commit secrets, `.env`, real employee data, databases, or the source PDFs/DOCX.
- Commit or push only when Amulya asks.
