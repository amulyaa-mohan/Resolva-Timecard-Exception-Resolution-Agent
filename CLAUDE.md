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
- Prompts: `propose_v2` (default; adds a trusted `<facts>` block with local dates) and `propose_v1`.
- Evals: `cd backend && python -m evals.run` (36 labelled cases, 18 scripted unsafe outputs, 12 retrieval
  cases). CI (`.github/workflows/ci.yml`) runs lint, format, pytest, eval gates, frontend build.
  Live reports at c6bde83 (Qwen2.5-7B): v1 83% proposal accuracy, v2 100% (two runs); 0 unsafe
  eligible and 100% injection resistance in all runs. Numbers are in docs/MODEL_CARD.md. Validator in
  evals is a stand-in. Real-model results vary run to run; rely on the deterministic gates.
- Latest live report (475b4cc, prompt v2 + language): all 6 live gates pass, proposal accuracy 100%,
  p50 4.23 s, lexicon intents 100% in en/hi/kn, paraphrases 10/12 (safe misses).
- Tests: 223 passing (incl. Track A). `tzdata` is a runtime dependency (Windows/slim images). Local Ollama in Docker: `cd backend && docker compose -f docker-compose.yml
  -f docker-compose.gpu.yml --profile ollama up -d ollama` (models persist in the `ollama-models` volume).

## Next up

1. Jayanth adopts 0.2.0 (outcomes, evidence_ref tolerance, week_start, as_of excluded from his
   hash). Then make `as_of` required and freeze SHARED-01; update frontend `contracts.ts`.
1b. Evals: complete evidence per case, incomplete cases expecting ESCALATED, report stub vs real
   `validate_correction` side by side; then gate CI on the real one and re-run live evals.
2. SHARED-02 with Jayanth: first end-to-end missing-punch flow through his routes; wire
   `ExceptionQuery` filters into his exception list.
3. Ask native Hindi/Kannada speakers to review the lexicons and reply templates.
4. Optional: intent prompt v2 with few-shot examples to lift paraphrase accuracy (measure first).

## Working agreements for Claude

- Before work: `git fetch`, read new teammate commits, and integrate `main` if it moved. Never overwrite Jayanth's files.
- Mock-provider results prove the harness, not model quality. Never present them as model accuracy.
- Never commit secrets, `.env`, real employee data, databases, or the source PDFs/DOCX.
- Commit or push only when Amulya asks.
