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

## Current state (2026-11-17, after B-03)

- Branch `backend` (on top of `main` 68ede72). B-01/B-02 in 3874367; B-03 in the following commit.
- SHARED-01: draft contracts `0.1.0-draft`, awaiting Jayanth's review (11 decisions in
  TRACK_B_INTEGRATION.md section 5). Track A's validator must return at least one `RuleCheck`.
- B-01, B-02, B-03 in REVIEW. Pipeline order: kill-switch -> policy applicable -> pre-model evidence gate
  (`app/ai/evidence.py`) -> hybrid retrieval -> model (hard 8 s budget, 1 repair retry) -> schema ->
  exception id -> allowed actions -> citations retrieved + verbatim (>= 5 words) -> validator (non-empty)
  -> missing info -> confidence.
- Providers: mock (default), Ollama `qwen2.5:7b-instruct`, Groq `llama-3.1-8b-instant` (Groq tested only
  with mocked HTTP). Retrieval: BM25 + embeddings with RRF (ADR-006); hashing embedder by default,
  `nomic-embed-text` via Ollama optional. Packs: IN-KA@2025.1, IN-KA@2025.2-proposed (never resolved), US-FED@2025.1.
- Tests: 91 passing. Live Ollama smoke check (`backend/scripts/live_check.py`): 6/6 after the evidence-gate
  fix, warm latency 2-5 s; cold model load 30-60 s, so warm up before demos.
- Local Ollama runs in Docker: `cd backend && docker compose -f docker-compose.yml -f docker-compose.gpu.yml
  --profile ollama up -d ollama` (models persist in the `ollama-models` volume).

## Next up

1. B-05: labelled eval cases in `backend/evals/` (clear / ambiguous / adversarial / jurisdiction-flip),
   `evals/run.py` reporting real numbers, GitHub Actions CI with an eval gate.
2. B-04: English/Kannada/Hindi intents with parity tests.
3. When Track A lands A-02: replace stub validators in live_check/evals with `validate_correction`.

## Working agreements for Claude

- Before work: `git fetch`, read new teammate commits, and integrate `main` if it moved. Never overwrite Jayanth's files.
- Mock-provider results prove the harness, not model quality. Never present them as model accuracy.
- Never commit secrets, `.env`, real employee data, databases, or the source PDFs/DOCX.
- Commit or push only when Amulya asks.
