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

## Current state (2026-11-17)

- Branch `backend`, based on `main` 68ede72 (Jayanth's two-folder layout).
- SHARED-01: draft contracts `0.1.0-draft` in `backend/app/core/contracts.py`, awaiting Jayanth's review
  (10 open decisions listed in TRACK_B_INTEGRATION.md section 5).
- B-01 (REVIEW): settings + kill-switch, RFC 7807 errors, `X-Trace-Id`, `/health` with AI mode,
  provider interface + offline `MockProvider`, Dockerfile + compose. Verified: clean install, server, Docker.
- B-02 (REVIEW): IN-KA@2025.1 policy pack, registry + `resolve_policy`, version-filtered keyword retrieval,
  `prompts/propose_v1.md`, `generate_proposal` with gates (schema + 1 repair retry, allowed actions,
  citation membership, verbatim quote of at least 5 words, validator, missing info, confidence).
- Tests: 43 passing. The validator is a test stub until Track A's A-02 lands.

## Next up

1. B-03: Ollama and Groq providers (real timeout enforcement), hybrid keyword + vector retrieval,
   US-FED (+CA) pack and IN-KA@2025.2-proposed pack for wrong-version tests, an overlapping-shift clause.
2. B-04: English/Kannada/Hindi intents with parity tests.
3. B-05: GitHub Actions CI and `backend/evals/` with measured results (feeds slide 4).

## Working agreements for Claude

- Before work: `git fetch`, read new teammate commits, and integrate `main` if it moved. Never overwrite Jayanth's files.
- Mock-provider results prove the harness, not model quality. Never present them as model accuracy.
- Never commit secrets, `.env`, real employee data, databases, or the source PDFs/DOCX.
- Commit or push only when Amulya asks.
