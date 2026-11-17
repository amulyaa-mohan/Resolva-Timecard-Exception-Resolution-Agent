# Shared development updates

Read alongside `docs/TASKS.md` before each session. Append an entry after meaningful work and before committing or handing off.
Keep earlier entries intact. Use explicit dates and time zones when recording times.
Never include credentials, private employee data, or invented test results.

## Entry template

### YYYY-MM-DD — Developer — Task ID — Short summary

- Branch:
- Status: IN PROGRESS / BLOCKED / REVIEW / DONE
- Changed: files/modules and behavior added or modified.
- Contracts: interface changes, or none.
- Validation: exact checks run and outcomes; say not run when applicable.
- Dependencies/blockers:
- Next step:
- Publication: local only / pushed branch / PR link. Add commit reference after it exists if useful; do not amend history just to record its own hash.

## Updates

### 2026-11-17 — C V Jayanth — COORD-01 — Shared coordination foundation

- Branch: `cv-jayanth`
- Status: REVIEW
- Changed: added AGENTS.md, docs/TEAM_RULES.md, docs/TASKS.md, docs/START_HERE.md, and UPDATE.md.
- Contracts: documented proposed integration interfaces; schemas still require joint agreement.
- Validation: documentation paths and required sections inspected; Git staged whitespace check passed. No application tests exist yet.
- Dependencies/blockers: teammate identity and integration branch remain to be agreed.
- Next step: teammate reads the shared rules; both developers agree SHARED-01.
- Publication: included in the coordination commit for `cv-jayanth`; remote publication is verified separately after push.

### 2026-11-17 — C V Jayanth — COORD-02 — Shared team branches

- Branch: `main`; new team branches: `frontend`, `backend`, `database`.
- Status: BLOCKED (default-branch migration only).
- Changed: updated README and team guides for shared branch ownership and safe collaboration.
- Contracts: database work uses `database` and coordinates schema changes with backend owners.
- Validation: remote inventory confirmed only cv-jayanth existed; GitHub rename API returned 403 requiring admin access. Whitespace check performed before commit.
- Dependencies/blockers: repository owner must set `main` as default; retain cv-jayanth until then.
- Next step: publish main and the three team branches; owner changes default; retire old branch afterward.
- Publication: branch creation is verified separately after push.

### 2026-11-17 — C V Jayanth — SCAFFOLD-01 — Local runnable workspace

- Branch: `backend`.
- Status: REVIEW.
- Changed: cloned repository to Desktop/dayforce; added FastAPI health endpoint, React/TypeScript/Vite connection page, module ownership directories, database/test/evaluation boundaries, dependency snapshots, and local setup documentation.
- Contracts: business schemas remain pending SHARED-01; only GET /health is implemented. Cross-team scaffold is supplied for review at the user's request.
- Validation: pytest 1 passed; Ruff passed after import formatting; TypeScript/Vite production build passed; live API and Vite-proxied health returned status ok; Git whitespace check passed. npm install reported zero vulnerabilities. Test client reports one upstream httpx deprecation warning.
- Dependencies/blockers: business rules, authentication, database migrations, AI, Docker and CI remain future tasks; no claim of complete application functionality.
- Next step: team reviews scaffold and agrees SHARED-01 contracts; assign database and frontend tasks.
- Publication: local only; no commit or push made for this scaffold.

### 2026-11-17 — C V Jayanth — COORD-03 — Backend coordination documents

- Branch: `backend`.
- Status: REVIEW.
- Changed: moved detailed agent instructions and the complete update history to backend/docs/AGENTS.md and backend/docs/UPDATE.md; retained a minimal root AGENTS.md discovery pointer and updated active references.
- Contracts: none; instruction paths are explicitly relative to the repository root.
- Validation: verified both destination files and root pointer; Git whitespace check passed. Documentation-only change; application tests not repeated.
- Dependencies/blockers: none.
- Next step: use backend/docs for agent instructions and future update entries.
- Publication: local only; not committed or pushed.

### 2026-11-17 — C V Jayanth — COORD-04 — Multi-team agent routing

- Branch: backend; status REVIEW.
- Changed: area-specific agent guides, task indexes, progress logs, frontend build plan, root/area routing and shared contract coordination document.
- Contracts: clarified database migration ownership and backend liaison; business interfaces still pending agreement.
- Validation: all referenced area documents exist; Git whitespace check passed. Documentation-only change; runtime tests not repeated.
- Next step: review and publish the scaffold plus guidance so remote clones can discover it.
- Publication: local only; no commit or push.

### 2026-11-17 — C V Jayanth — SCAFFOLD-01 / COORD-04 — Publication handoff

- Branch: backend; status REVIEW.
- Changed: publishing the runnable scaffold and all three teams' agent instructions, task trackers and progress logs at the user's request.
- Validation: scaffold previously passed backend smoke test, lint, frontend build and live API proxy check; documentation paths and whitespace rechecked before commit.
- Contracts: domain interfaces remain pending SHARED-01.
- Next step: teammates review this backend branch; integrate into main and team branches through reviewed changes.
- Publication: authorized for commit and push to backend; final push result reported in the chat. Other branches are not updated by this push.

### 2026-11-17 — C V Jayanth — COORD-02 — Main publication and branch cleanup

- Branch: main; status DONE for branch migration.
- Changed: published scaffold to main; confirmed GitHub default is main; removed obsolete cv-jayanth branch with its history preserved in main.
- Validation: GitHub default-branch API and successful remote push/deletion responses checked; documentation whitespace checked.
- Next step: synchronize backend, frontend and database to this shared baseline; teammates fetch before work.
- Publication: main scaffold published; coordination update included in the following baseline synchronization commit.

### 2026-11-17 — C V Jayanth — COORD-05 — Two-folder repository layout

- Branch: main; status REVIEW.
- Changed: consolidated database, policies, prompts, fixtures, evaluations and scripts under backend; shared guides now backend/docs/shared. Frontend remains self-contained. Root keeps README, agent routing and Git ignore rules.
- Configuration: backend/.env.example and backend/.env are now the backend configuration paths, resolved independently of launch directory.
- Validation: backend smoke test passed (one upstream deprecation warning); Ruff passed; TypeScript/Vite build passed; active instruction paths and whitespace checked.
- History: earlier update entries retain their original paths as historical records.
- Next step: teammates bring the main reorganization into their working branches before new work.
- Publication: user authorized direct commit and push to main; team branches are not changed by this operation.

### 2026-11-17 — Amulya Mohan — SHARED-01 / B-01 / B-02 — Contracts draft, AI pipeline, verification, integration docs

- Branch: `backend`, rebased onto `main` 68ede72 (two-folder layout) before committing.
- Status: REVIEW.
- Changed:
  - Draft SHARED-01 contracts `0.1.0-draft` in `backend/app/core/contracts.py`; RFC 7807 errors (`core/errors.py`) and `X-Trace-Id` propagation (`core/tracing.py`), proposed as shared infrastructure.
  - B-01: AI settings and kill-switch merged into the scaffold `Settings` (unprefixed env vars, `backend/.env`); `/health` keeps the scaffold fields and adds `contract_version`, `ai_enabled`, `llm_provider`, `llm_status`, `mode`; provider interface and offline `MockProvider`; `backend/Dockerfile` and `backend/docker-compose.yml`.
  - B-02: IN-KA@2025.1 policy pack (YAML rules + 10-clause handbook), registry and `resolve_policy`, version-filtered keyword retrieval, `prompts/propose_v1.md`, and `generate_proposal` gates: schema with 1 repair retry, exception match, allowed actions, citation membership, verbatim quote of at least 5 words, validator (a crash blocks), missing information, confidence.
  - Verification fixes: trivial or empty citation quotes no longer pass; trace raw output is capped at 20,000 chars; one Markdown code fence around JSON is accepted.
  - Touched scaffold files: `main.py`, `config.py`, `pyproject.toml`, `.env.example` merged (CORS and env location kept); `tests/test_health.py` now asserts the three scaffold fields instead of exact equality; `requirements-dev.lock` marks `uvloop` as non-Windows (it failed to install on Windows); root `.gitignore` adds `venv/`; ruff config added (E501 not selected; the formatter owns line length).
  - Docs: `CLAUDE.md` at the root (imports AGENTS.md); `backend/docs/shared/TRACK_B_INTEGRATION.md` (Codex-ready guide for Track A); pointer added in `backend/docs/AGENTS.md`; STRUCTURE, CONTRACTS, LOCAL_DEVELOPMENT, module READMEs and task trackers updated.
- Contracts: draft only. Differences from the design doc: escalations need no citations; `ProposedAction.punch_type`; `CaseContext.evidence_version` owned by Track A; `ProposalResult.status` is eligible/blocked/escalated. Ten open decisions are listed in TRACK_B_INTEGRATION.md section 5.
- Validation (actually run, Windows): clean venv install from `requirements-dev.lock` + `-e backend[dev]` succeeded after the uvloop marker; `pytest backend/tests`: 43 passed; `ruff check backend` and `ruff format --check backend` passed; 20 adversarial pipeline probes passed; live uvicorn `/health`, `/docs`, `/openapi.json` OK, 404/405 return problem+json, unsafe trace headers are replaced; `AI_ENABLED=false` gives `rules_only`; `docker compose up --build` gives a healthy container that loads IN-KA@2025.1 and the prompt. Frontend build not run (no frontend changes). Mock results do not measure model quality.
- Dependencies/blockers: real `validate_correction` (A-02) and `build_case_context` (A-01/A-02); SHARED-01 agreement.
- Next step: Jayanth reviews the contracts; Amulya starts B-03 (Ollama/Groq, hybrid retrieval, US-FED and IN-KA@2025.2-proposed packs).
- Publication: committed locally on `backend`; not pushed.

### 2026-11-17 — Amulya Mohan — B-03 — Real providers, hybrid retrieval, evidence gates

- Branch: `backend`.
- Status: REVIEW.
- Changed:
  - Providers: `OllamaProvider` (JSON mode, `keep_alive` 30 m) and `GroqProvider` (OpenAI-compatible, key held as `SecretStr`, never in errors or repr) in `app/ai/providers/http.py`; `build_provider` picks one from settings; `LLM_MODEL` unset means the provider default.
  - Pipeline: one hard wall-clock budget (`LLM_TIMEOUT_S`) per generation, repair retry included, enforced even if a provider ignores its timeout; any adapter exception escalates; new pre-model evidence gate (`app/ai/evidence.py`); a validation result with no rule checks now blocks.
  - Retrieval: `app/retrieval/hybrid.py` (pack/version filter, BM25 + embeddings, reciprocal rank fusion, per-embedder relevance floors, BM25-only fallback recorded in `gate_checks`); `HashingEmbedder` (offline) and `OllamaEmbedder` (`nomic-embed-text`). Decision recorded in `docs/shared/adr/ADR-006`.
  - Policy packs: IN-KA@2025.1 gains KA-11 (overlapping records); new IN-KA@2025.2-proposed (status `proposed`, near-duplicate clauses) and US-FED@2025.1 (federal + California overlay).
  - Packaging: optional `ollama` Compose profile (image pinned to 0.40.16, named volume for models) and `docker-compose.gpu.yml`; `httpx` moved to runtime dependencies (the container failed to import without it).
  - Docs: `docs/MODEL_CARD.md`, ADR-006, `scripts/live_check.py`, LOCAL_DEVELOPMENT, TRACK_B_INTEGRATION (validator must return at least one check; evidence gate; decision 11 on `detection_details` keys), `.env.example`.
- Contracts: no change to `contracts.py`. New expectations for Track A: `validate_correction` returns at least one `RuleCheck`; proposed `detection_details` keys listed as decision 11.
- Validation (actually run): `pytest backend/tests`: 86 passed; ruff check and format clean. Retrieval top-1 on 11 code/pack pairs: 11/11 with the hashing embedder, 10/11 with `nomic-embed-text` (US overtime ranks the weekly clause US-2 above daily US-3; both relevant); US spread-over correctly retrieves nothing. Live check with `qwen2.5:7b-instruct` on Ollama (GPU): 5/6 before the evidence gate (no-schedule case invented 09:32 and was eligible), then 6/6 on three runs including inside Docker; warm latency 2.2-4.8 s; cold load 30-60 s. Groq verified only with mocked HTTP (no key used).
- Dependencies/blockers: real validator (A-02); `detection_details` keys for the remaining evidence rules (SHARED-01 decision 11).
- Next step: B-05 evaluation suite and CI (turn live_check cases into labelled eval cases with measured results); B-04 multilingual intents.
- Publication: superseded by the verification entry below.

### 2026-11-17 — Amulya Mohan — B-03 — Verification pass before publication

- Branch: `backend`.
- Status: REVIEW.
- Changed: `/health` now builds the provider once per app (it previously opened an HTTP client per request and never closed it); hybrid retrieval now degrades to BM25-only on NaN similarities or malformed vectors (mismatched dimensions previously raised an unhandled ValueError); tests added for both, plus `/health` with Groq unconfigured and Ollama unreachable.
- Contracts: none.
- Validation (actually run): fresh venv from `requirements-dev.lock` + `-e backend[dev]` on Windows; `pytest backend/tests`: 91 passed (three runs); ruff check and format clean; 24/24 adversarial probes (malformed Ollama/Groq replies, HTTP 404/429, NaN and mismatched embeddings, 50 ms budget against a 500 ms model, every exception code in both packs, empty policy); `docker compose ... --profile ollama up --build` with the GPU override: API container healthy, live check 6/6 against `qwen2.5:7b-instruct` + `nomic-embed-text` inside Compose (p50 4.7 s, max 5.3 s; warm-up 9 s with cached model files). Groq still verified with mocked HTTP only.
- Dependencies/blockers: unchanged (A-02 validator; SHARED-01 decisions).
- Next step: B-05 evaluation suite and CI.
- Publication: committed and pushed to `backend` with this entry.

### 2026-11-17 — Amulya Mohan — B-05 — Evaluation harness, CI, and pipeline fixes found by evaluation

- Branch: `backend`.
- Status: REVIEW.
- Changed:
  - Evaluation (`backend/evals/`): case format and builders (`schema.py`); 36 labelled MISSING_PUNCH cases (12 clear incl. overnight shifts, 8 ambiguous, 8 adversarial incl. Hindi/Kannada injections, 8 jurisdiction-flip); 12 retrieval cases; 18 scripted unsafe model outputs (`safety_cases.py`) each mapped to the gate that must stop it; `run.py` producing Markdown + JSON reports with git commit, model, prompt and validator, and `ci`/`live` gate profiles; stand-in window validator (`stub_validator.py`, replaced when A-02 lands).
  - CI: `.github/workflows/ci.yml` (backend lint, format, pytest, offline eval gates with summary + artifact; frontend typecheck + build). `backend/docs/CI.md` documents it.
  - Pipeline fixes found by evaluation: pre-model gate now also escalates when an employee note mentions a time outside the inference window (policy forbids inference when evidence contradicts the schedule; parses 24 h, dotted and am/pm times, ignores dates/decimals); escalations now strip citations that are not verbatim retrieved clauses (live Qwen escalated while citing an invented KA-99); prompt `propose_v2` adds a trusted `<facts>` block with local dates (live Qwen v1 put overnight clock-outs on the wrong day); `PROMPT_VERSION` setting (default v2).
  - Docs: CONTRACTS.md frontend alignment notes (read-only comparison with `origin/frontend` types); TRACK_B_INTEGRATION.md (validator must enforce the inference window; evaluating with the real validator); LOCAL_DEVELOPMENT, eval READMEs, `.env.example`, CLAUDE.md.
- Contracts: none changed. New Track A expectation: `validate_correction` enforces the missing-punch inference window and punch pairing.
- Validation (actually run): clean venv from `requirements-dev.lock`; ruff check and format clean; `pytest`: 119 passed; `python -m evals.run --gates ci` (mock): all six gates pass, 18/18 safety cases stopped by their expected gate. Preview live runs on Qwen2.5-7B before the last two fixes: v1 proposal accuracy 83%, v2 100%, all live gates passing; final reports are regenerated from the committed code in the next commit. Frontend: `tsc --noEmit` passes locally; the Vite build could not run on this Windows machine (Application Control blocked Rollup's native binary), so the CI frontend job is its first full build.
- Dependencies/blockers: real validator (A-02); `detection_details` keys (SHARED-01 decision 11).
- Next step: commit live reports; B-04.
- Publication: committed and pushed to `backend`; CI result checked on GitHub.

### 2026-11-17 — Amulya Mohan — B-05 — Time-evidence gate (found by a live eval re-run)

- Branch: `backend`.
- Status: REVIEW.
- Changed: new deterministic `time_evidence` gate (`app/ai/evidence.py::unanchored_times`, called in the pipeline before the validator): an added punch must be within 5 minutes of the scheduled start/end (full date and time), a time the employee stated in a note, or a same-weekday history punch of the same type. Two new safety cases (s19 edge-of-window 18:30, s20 right time on the wrong day; 20 in total); s10 is now stopped earlier by this gate. Eval report notes run-to-run variation. CI actions moved to v7 (v4/v5 targeted the deprecated Node 20 runtime).
- Why: re-running the v2 live eval at 2099dc5 produced one unsafe eligible proposal. Case x08's note asked for a clock-out "four hours after the scheduled end"; Qwen proposed 18:30 for an 18:00 end, the very edge of the 30-minute inference window, and the stand-in window validator allowed it. The window bounds deviation; it does not justify it. The earlier two v2 runs did not show this, so single runs can hide rare failures.
- Contracts: none.
- Validation (actually run): ruff clean; `pytest`: 124 passed; mock eval passes all CI gates; 20/20 safety cases stopped by their expected gate. CI for 2099dc5 passed on GitHub (backend and frontend jobs).
- Next step: re-run live evals at this commit and commit the reports; then B-04.
- Publication: committed and pushed to `backend`.
