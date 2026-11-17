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

## Current state (2026-11-17, after B-05)

- Branch `backend` (on top of `main` 68ede72). B-01/B-02 3874367, B-03 ef619b6, B-05 2099dc5 +
  c6bde83 (time-evidence gate) + live reports. CI green on GitHub for each push.
- SHARED-01: draft contracts `0.1.0-draft`, awaiting Jayanth's review (11 decisions in
  TRACK_B_INTEGRATION.md section 5). His validator must return at least one `RuleCheck` and enforce the
  missing-punch inference window. Frontend type mismatches are listed in backend/docs/shared/CONTRACTS.md.
- B-01, B-02, B-03, B-05 in REVIEW; B-04 (multilingual intents) is next.
- Pipeline order: kill-switch -> policy applicable -> pre-model evidence gate (`app/ai/evidence.py`: no
  schedule/history, or a note time conflicting with the schedule) -> hybrid retrieval -> model (8 s budget,
  1 repair retry) -> schema -> exception id -> escalation citations stripped if unverified -> allowed
  actions -> time evidence (added punch within 5 min of schedule/stated time/history) -> citations
  retrieved + verbatim -> validator (non-empty) -> missing info -> confidence.
- Prompts: `propose_v2` (default; adds a trusted `<facts>` block with local dates) and `propose_v1`.
- Evals: `cd backend && python -m evals.run` (36 labelled cases, 18 scripted unsafe outputs, 12 retrieval
  cases). CI (`.github/workflows/ci.yml`) runs lint, format, pytest, eval gates, frontend build.
  Live reports at c6bde83 (Qwen2.5-7B): v1 83% proposal accuracy, v2 100% (two runs); 0 unsafe
  eligible and 100% injection resistance in all runs. Numbers are in docs/MODEL_CARD.md. Validator in
  evals is a stand-in. Real-model results vary run to run; rely on the deterministic gates.
- Tests: 124 passing. Local Ollama in Docker: `cd backend && docker compose -f docker-compose.yml
  -f docker-compose.gpu.yml --profile ollama up -d ollama` (models persist in the `ollama-models` volume).

## Next up

1. B-04: English/Kannada/Hindi intents with parity tests (add parity cases to the eval).
2. When Track A lands A-02: swap `validate_correction` into evals and live_check; re-run live evals.
3. SHARED-02 with Jayanth: first end-to-end missing-punch flow through his routes.

## Working agreements for Claude

- Before work: `git fetch`, read new teammate commits, and integrate `main` if it moved. Never overwrite Jayanth's files.
- Mock-provider results prove the harness, not model quality. Never present them as model accuracy.
- Never commit secrets, `.env`, real employee data, databases, or the source PDFs/DOCX.
- Commit or push only when Amulya asks.
