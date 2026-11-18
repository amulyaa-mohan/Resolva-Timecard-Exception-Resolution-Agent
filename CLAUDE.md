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

## Current state (2026-11-18, hand-in)

- **`main` = `backend` at 34c2506** (PR #13, after Track A's PR #12). CI green on `main`: 639 tests
  on a `postgres:15` service (the build fails if any PostgreSQL test skips), ruff, eval gates,
  frontend build.
- **Working end to end** (verified on the Docker stack with live Qwen2.5-7B on the GPU): import ->
  detection (six exception types) -> manager list/detail -> AI proposal (gates + Track A's real
  validator) -> approve/reject/escalate (idempotent, stale-checked, append-only, hash-chained audit)
  -> effective timecard. HTTP walk-through 49/49, 0 server errors; demo story: approve Tuesday's
  missing punch, then Friday's late arrival becomes eligible and is approved to the stated 09:05.
- **AI proposals:** MISSING_PUNCH (`add_punch`) and, via `adjust_punch` to a time the employee stated,
  SCHEDULE_DEVIATION, SPREAD_OVER_BREACH and OVERLAPPING_SHIFT. Prompt `propose_v3` (default).
  Unsupported fix types (`add_break`, `void_shift`, `flag_premium`, `acknowledge`, schedule swaps)
  escalate to the manager. An evidenced fix leaving only warnings escalates; problems block.
- **Contract:** SHARED-01 `0.2.0-draft`, adopted by both tracks (not frozen; see Future work).
- **Evals:** `cd backend && python -m evals.run` (58 labelled cases incl. 13 adjustment and 9
  evidence-gap cases, 20 scripted unsafe outputs, 12 retrieval cases), validated by Track A's rules.
  Final live run on the merged code: 100% in every category, 0 unsafe, 0 repair retries, p50 4.45 s.
  Numbers: `backend/docs/MODEL_CARD.md`. Audit: `backend/docs/shared/AUDIT_2026-11-18.md`.
- **Local setup notes:** `docker compose --profile postgres` for PostgreSQL; Ollama:
  `cd backend && docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d
  ollama`. If Windows Application Control blocks the psycopg DLL (it did on 2026-11-18; settings were
  not changed), run tests and seeding in `python:3.12-slim` on the compose network (UPDATE.md).

## Next up (future work, out of scope for the 2026-11-18 deadline)

1. Contract `0.3.0`: `new_end_ts` (add_break), `target_punch_ids` (void_shift), `acknowledge` with a
   manager reason, schedule swaps never approvable, and a "roster final" signal so an unscheduled
   shift can become a SCHEDULE_DEVIATION warning. Until then those cases escalate safely.
2. Freeze SHARED-01 (drop `-draft`, make `as_of` required) and update frontend `contracts.ts`.
3. Native Hindi/Kannada review of the lexicons and reply templates.
4. Optional: intent prompt with few-shot examples (paraphrases 10/12 today, misses fail safe).

## Working agreements for Claude

- Before work: `git fetch`, read new teammate commits, and integrate `main` if it moved. Never overwrite Jayanth's files.
- Mock-provider results prove the harness, not model quality. Never present them as model accuracy.
- Never commit secrets, `.env`, real employee data, databases, or the source PDFs/DOCX.
- Commit or push only when Amulya asks.
