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

### 2026-11-17 — Amulya Mohan — B-05 — Live evaluation reports

- Branch: `backend`.
- Status: REVIEW.
- Changed: `backend/evals/reports/ollama-qwen2.5-7b-instruct-propose_v1.*`, `...-propose_v2.*` and `...-propose_v2-run2.*`, all generated from clean commit c6bde83 (each report records it); results table in `docs/MODEL_CARD.md`; CLAUDE.md.
- Results: v1 proposal accuracy 83% (overnight shifts on the wrong day, all blocked); v2 100% in both runs; escalation recall 100% everywhere, precision 75% (v1) and 100% (v2); 0 unsafe eligible, 100% injection resistance, 100% harness block rate (20 cases), 100% retrieval top-1 and 0 leakage in all three runs; latency p50 4.40 s (v1) and 5.37/5.54 s (v2), p95 at most 5.95 s.
- Contracts: none.
- Validation: the three runs above; CI for c6bde83 passed on GitHub (backend and frontend jobs, actions v7, no Node 20 deprecation warnings).
- Next step: B-04.
- Publication: committed and pushed to `backend`.

### 2026-11-17 — Amulya Mohan — B-04 — Multilingual intents and AI fallback

- Branch: `backend`.
- Status: REVIEW.
- Changed:
  - `backend/app/language/`: `Intent` schema (LIST/COUNT/SHOW/EXPLAIN or UNSUPPORTED with a reason), script-based language detection, en/hi/kn lexicon parser with a confidence flag, LLM fallback (`prompts/intent_v1.md`; JSON mode; schema-validated; ids must appear verbatim in the request; timeouts and bad output fall back), fixed localized reply templates that keep ids/codes canonical, `ExceptionQuery` filters for Track A, `resolve_dates()`; `POST /assistant/query` (CORS now allows POST).
  - Read-only by design: approve/reject/edit/delete/add requests are refused in every language.
  - Evals: `evals/language_cases.json` (13 commands x 3 languages), `evals/language_paraphrases.json` (4 x 3, LLM-only), `evals/language_eval.py`; new CI and live gates `language_parity` and `language_write_refusal`; Markdown report section.
  - Fix during development: a parse built only from a date ("anyone who didn't punch out today?" -> "today") is no longer treated as confident, so it no longer hides the request's meaning from the LLM.
- Contracts: new HTTP endpoint documented in CONTRACTS.md; shared `contracts.py` unchanged.
- Validation (actually run): ruff clean; `pytest`: 159 passed; `python -m evals.run` (mock) passes all 8 CI gates, lexicon parity 100% and write refusal 100% with AI off. Live Qwen2.5-7B paraphrase check: 10/12 correct (en 4/4, hi 3/4, kn 3/4); both misses were invalid model outputs (an EXPLAIN without an id; a COUNT with a stray reason) rejected by the schema, falling back to a partial parse or "not understood".
- Dependencies/blockers: Track A's exception list must accept `ExceptionQuery` filters to return results; native-speaker review of Hindi/Kannada lexicons and templates.
- Next step: live eval report including the language section; SHARED-02 once A-02/A-03 land.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-17 — Amulya Mohan — B-04 — Verification pass

- Branch: `backend`.
- Status: REVIEW.
- Changed (defects found and fixed):
  - Hindi "कल" (yesterday) matched inside "निकल" (left) and "सकल" (total); Indic phrases now start on a word boundary, and words of three characters or fewer must also end on one (suffixes like पंचों and ಪಂಚ್‌ಗಳನ್ನು still match).
  - Ids embedded in other tokens were picked up ("TIME-OFF" became employee E-OFF; "TAX-2026" opened exception X-2026); ids must now not follow a letter, digit or dash.
  - "last week" was silently dropped; LAST_WEEK is now supported in all three languages, the intent prompt and `resolve_dates`.
  - Live Qwen added filters nobody asked for ("Who skipped lunch?" -> severity=problem, status=open); severity, status and employee_id now come only from the deterministic parse, and dropped extras are recorded in `IntentResult.dropped_filters`.
  - One test passed for the wrong reason (the lexicon answered, so the model path was never exercised); rewritten to assert the real behaviour.
- Validation (actually run): clean venv from `requirements-dev.lock`; ruff check and format clean; `pytest`: 171 passed; `python -m evals.run` (mock) passes all 8 CI gates; 15/15 adversarial probes (word boundaries, embedded ids, write refusal with ZWNJ noise, mixed scripts, romanised Hindi, NFD input, injection via the request, tag breakout, 5000-char and blank input). Live HTTP: rules-only server 42/42 lexicon requests correct with 14/14 parity; Qwen-backed server 42/42 lexicon (no model calls) and 10/12 paraphrases in two consecutive runs (same two misses, both invalid model outputs rejected by the schema, failing safe); paraphrase latency p50 3.6-4.1 s, max 7.2 s. In-process parse 0.2 ms; HTTP with keep-alive 2.5 ms. On Windows, `localhost` adds about 2 s per request (IPv6 fallback); documented to use 127.0.0.1.
- Dependencies/blockers: unchanged.
- Next step: commit and push when authorised; then a live eval report including the language section.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-17 — C V Jayanth — A-START-01 — Attendance domain and first rule

- Branch: backend; status REVIEW.
- Changed: draft immutable attendance DTOs, shift-scoped missing-punch detector, non-mutating added-punch simulation, synthetic overnight fixture and boundary tests.
- Contracts: proposed in backend/docs/shared/CONTRACTS.md; not frozen or exposed as an API. No database or teammate AI modules changed.
- Validation: pytest 13 passed; Ruff check passed; Git whitespace check passed. Existing test-client dependency emits one upstream deprecation warning.
- Limitations: only missing-punch pairing is implemented; approval eligibility remains false. Persistence, authorization, evidence grounding, remaining rules and HTTP endpoints are pending.
- Next step: review domain contract with teammate/database owner, then connect persistence/permissions and expand validation.
- Publication: local only, not committed or pushed.

### 2026-11-18 — C V Jayanth — SHARED-01 / A-INTEGRATE-01 — Track B integration and contract answers

- Branch: backend; status REVIEW for integration boundary; A-01/A-02 remain IN PROGRESS.
- Integrated remote Track B commit 3874367 via fast-forward; restored local Track A work and preserved both update histories. A pre-integration stash remains as a backup.
- Changed: CaseService, canonical evidence hashing, consistency checks, assigned-manager repository access, disposable SQLite snapshot persistence, and a CorrectionValidator-compatible adapter that reuses the missing-punch detector.
- Contract answers (details in backend/docs/shared/TRACK_A_CONTRACT_RESPONSE.md):
  1. Accept opaque IDs; enforce nonempty at boundaries.
  2. Accept local shift-start work date, including overnight shifts.
  3. SHA-256 canonical evidence JSON plus correction revision; policy and permission checks separate.
  4. Target resolution and no new warnings/problems; incomplete checks block approval.
  5. Propose explicit action targets now; unsupported actions remain rejected until agreed.
  6. Accept shared ProposedAction for manual and AI corrections with identical validation.
  7. Track A audit includes actor, evidence versions, rule/policy/model/prompt trace references and atomic correction linkage.
  8. Accept proposal/trace tables; final relational schema/migrations remain database-team work.
  9. Accept Track A exception/proposal route ownership; authenticated identity dependency still pending.
  10. Accept DEFAULT_SEVERITY mapping and validate it at case load.
- Shared contracts and Track B implementation modules were not changed; version remains 0.1.0-draft pending joint agreement.
- Validation: 63 pytest tests passed; Ruff lint passed; Ruff format check passed for 79 files; Git whitespace check passed. One existing upstream test-client deprecation warning remains.
- Limits: SQLite adapter is disposable integration storage, not production migrations. manager_id is an internal trusted argument, not authentication. No domain HTTP endpoints, full six-rule validator or approval writes exist yet. Mock proposals remain BLOCKED with the partial validator.
- Next step: Amulya reviews responses; database team agrees schema/repository implementation; Track A adds authenticated API access and remaining deterministic rules before enabling approval.
- Publication: local only; no commit or push made.

### 2026-11-18 — C V Jayanth — GitHub backend synchronization

- Fast-forwarded backend from 3874367 to origin/backend 475b4cc at the user's request.
- Restored existing Track A work; reconciled UPDATE.md and CONTRACTS.md by preserving both developers' additions. Backup stash codex-before-github-update-2026-11-18 retained.
- Validation: 191 backend tests passed (one upstream test-client deprecation warning); Ruff check passed.
- Task statuses unchanged by synchronization; Track A work remains local pending review.
- Publication: no new commit or push.

### 2026-11-18 — C V Jayanth — A-INTEGRATE-01 — Clash check and publication

- Branch: backend; status REVIEW.
- Base: latest Track B commit 475b4cc, including B-03/B-04/B-05 work.
- Conflicts: resolved shared UPDATE.md and CONTRACTS.md by preserving Track B additions and Track A entries; no source-code clashes found.
- Validation: 191 tests passed; Ruff lint and format passed (106 files); all eight offline CI evaluation gates passed. Offline eval uses its existing stand-in validator; real Track A integration is separately tested to block incomplete approval checks.
- Caveat: one existing upstream httpx test-client deprecation warning. No live-model evaluation rerun.
- Publication: user authorized commit/push of Track A work and contract responses to backend; main and other team branches are unchanged.
- Next step: review/freeze shared decisions, then finish persistence/authentication and deterministic validation.

### 2026-11-18 — C V Jayanth — A-RULES-02 — Six deterministic demo-policy checks

- Branch: backend; status REVIEW for rule module, A-02/A-04 remain IN PROGRESS for complete integration.
- Changed: rules/engine.py provides six checks; validator.py simulates supported missing-punch actions and reruns that engine, preserving original evidence. Added 33 rule boundary/safety cases and RULE_ENGINE.md.
- Checks cover work pairing, overlap, observed breaks, daily/projected weekly/quarterly limits, spread and schedule tolerance. Elapsed durations use UTC; invalid/ambiguous evidence fails closed.
- Contracts: internal AggregateEvidence proposed for trusted complete work-date/week/quarter values. Shared contracts.py untouched; no client or model detection_details used as aggregate authority.
- Validation: 224 pytest tests passed; Ruff lint passed; 108 files passed format check; all eight offline evaluation gates passed; Git whitespace passed. One existing upstream test-client warning remains. Offline eval still uses its stand-in validator; production-adapter safety is tested separately.
- Limits: no API/database changes. Actual approval still blocked without trusted aggregate contract. Only exact schedule-anchored missing work punches supported; other actions, live as_of semantics and full schema integration pending.
- Next step: agree aggregate/evaluation/action contracts with Track B and database team, then wire complete evidence and authorized decision persistence.
- Publication: local only; not committed or pushed.

### 2026-11-18 — C V Jayanth — A-READ-API-01 — Persisted manager-scoped exception reads

- Branch: backend; status REVIEW; overall A-01 and approval workflow still incomplete.
- Changed: optional read-only exception list/detail APIs; separate attendance settings; expiring server-provisioned bearer credentials with stored digests; persistent manager assignment checks; synthetic provisioning CLI; API/setup docs.
- Filters: Track B-compatible exception type, severity, status, IDs, date presets/bounds, pagination and manager-scoped counts. Only open demo snapshots exist; escalation/decision persistence is pending.
- Shared changes: main.py registers optional attendance repository/router; backend/.env.example adds attendance settings; .gitignore excludes local identity files. Track B modules and shared contracts.py unchanged.
- Validation: 244 pytest tests passed; Ruff lint passed; 113 files passed formatting; synthetic provisioning plus authenticated list/detail smoke passed. One existing upstream test-client deprecation warning. No live model tests needed.
- Limits: demo SQLite snapshot store and static expiring credentials, not final migrations/SSO. No approval writes, complete persisted aggregate loader or atomic correction/audit yet. Permissions are checked server-side; request role headers cannot grant access.
- Next step: team reviews endpoint/aggregate contracts; database adapter and trusted aggregate source must be implemented before approval is enabled.
- Publication: local only; not committed or pushed.

### 2026-11-18 — C V Jayanth — A-RULES-03 — Real validator wired to the proposal pipeline

- Branch: backend; status REVIEW. A-02/A-04 remain IN PROGRESS. Builds on Codex's uncommitted A-RULES-02/A-READ-API-01 work, which was preserved unchanged except the edits listed here.
- Changed: validator.py adds make_validator(load_aggregates), which keeps the shared three-argument CorrectionValidator interface. A trusted aggregate source can let a fully evidenced missing-punch fix reach ELIGIBLE. validate_correction is unchanged in behaviour and still fails closed. If the loader raises, returns None or returns the wrong type, the correction is blocked. engine.py blocks contexts that contain a clock-in on another local date, so that time cannot be double-counted.
- Tests: tests/unit/test_validator_aggregates.py and tests/integration/test_real_validator_pipeline.py cover exact weekly/quarterly boundaries, missing aggregates versus zero, a crashing source, fixes that leave a meal-break violation or create overtime, detection/validation equality, overnight shifts, local-versus-UTC dates, DST fall-back (US-FED), unsupported or ambiguous actions, cross-employee evidence, and eligible/blocked/escalated outcomes through generate_proposal.
- Validation: 282 pytest passed (1 existing upstream warning); Ruff lint passed; 116 files formatted. Offline eval (`python -m evals.run --gates ci`): all 8 gates PASS, but this uses the STAND-IN validator stub-window-v1, not the real validator. The mock provider proves the harness only, not model quality. No live model run.
- Unresolved (TRACK_A_CONTRACT_RESPONSE.md, A-RULES-03 section): aggregate delivery, insufficient-evidence outcome versus BLOCKED, time-anchor semantics versus the 5-minute gate, the eval validator swap, week/quarter calendars and as_of.
- Limits: no production aggregate loader exists yet, so no running route produces ELIGIBLE. Only add_punch for a missing work punch is supported. No approval, persistence or audit.
- Next step: Amulya answers questions 1-4; then implement a DemoCaseRepository-backed aggregate loader and swap the real validator into evals.
- Publication: local only; not committed or pushed.

### 2026-11-18 — C V Jayanth — A-RULES-04 — Track B contract answers applied on the Track A side

- Branch: backend; status REVIEW. Amulya's answers to the five A-RULES-03 questions are recorded as agreed in TRACK_A_CONTRACT_RESPONSE.md.
- Changed: engine.py (now attendance-rules@0.3-draft).
  - Each check now has an explicit outcome: pass, violation or insufficient_evidence (evaluate_rule_outcomes).
  - AggregateEvidence carries week_start, quarter_start and an aware as_of. Totals for a different week or quarter, or without a period or as-of time, count as insufficient evidence.
  - The OVERTIME_RISK reason records the totals, periods and as-of time it used.
  - make_validator already re-reads totals on every call; a test now proves it.
- Shared files: no change to contracts.py or Track B modules. One assertion in test_track_a_boundary.py was updated for the new reason wording; the blocking behaviour is unchanged.
- Validation: 296 pytest passed (1 existing upstream warning); Ruff lint passed; 116 files formatted. Offline eval `--gates ci`: 8/8 PASS on the STAND-IN validator (stub-window-v1), with the mock provider. No live model run.
- Open: the Indian quarter definition still needs confirming; who authors 0.2.0 still needs Jayanth's confirmation.
- Next step: publish the backend branch so Amulya can pull it. After 0.2.0, populate the outcome field, add evidence_ref and the tolerance, and add week_start weekday checks and as_of open-shift handling.
- Publication: local only; not committed or pushed.

### 2026-11-18 — Amulya Mohan — B-04 / B-05 — Live report including multilingual intents

- Branch: `backend`.
- Status: REVIEW.
- Changed: `backend/evals/reports/ollama-qwen2.5-7b-instruct-propose_v2-with-language.{md,json}` generated from clean commit 475b4cc (2026-11-17 18:40 UTC); results added to `docs/MODEL_CARD.md` and CLAUDE.md.
- Results: all six live gates pass (unsafe eligible 0; injection resistance 100%; harness block rate 100% on 20 cases, each stopped by its expected gate; leakage 0; language parity 100%; write refusal 100%). Proposal accuracy 100% with every category at 100%; latency p50 4.23 s, p95 4.58 s. Lexicon intents 100% in English, Hindi and Kannada. Paraphrases 10/12 through the LLM fallback (same two safe misses as the verification runs).
- Also: synced Track A commit 1c8b820 (append-only UPDATE.md conflict, both entries kept). On
  Windows 15 Track A tests failed with `ZoneInfoNotFoundError` (no system IANA database);
  added `tzdata` as a runtime dependency (`pyproject.toml`, `requirements-dev.lock`).
- Contracts: none.
- Validation: the run above; the report records its commit, model, prompt and validator. After the
  sync: pytest 191 passed on Windows; ruff check and format clean; 8/8 CI eval gates pass.
- Next step: Jayanth reviews SHARED-01; PR from `backend` into `main` after review.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — Amulya Mohan — SHARED-01 — Contract 0.2.0-draft

- Branch: `backend`.
- Status: REVIEW (Track A to adopt and confirm).
- Changed: `app/core/contracts.py` to `0.2.0-draft`: `RuleOutcome` and `RuleCheck.outcome` (derived from `passed` when omitted; must agree with it); `ValidationResult(passed=True)` requires at least one check and all passing; `EvidenceKind`, `EvidenceRef`, `ProposedAction.evidence_ref`; `Weekday`; `PolicyRules.evidence_tolerance_min`, `week_start`, `quarter_start_month` (all three packs: 5, monday, 1); optional `CaseContext.as_of`.
- Pipeline: a `violation` blocks, `insufficient_evidence` (with no violation) escalates with the proposal kept; the time-evidence gate (`anchor_times`) uses the policy tolerance, attaches an `EvidenceRef` (schedule, then note, then history) before the validator runs, rejects a model-supplied ref that does not resolve, and blocks any added punch after `as_of`; `<facts>` states the evaluation time.
- Contracts: yes, SHARED-01 draft revision; handover table in TRACK_B_INTEGRATION.md 5a; CONTRACTS.md and shared TASKS.md updated. No Track A files changed. `build_verified_case` should exclude `as_of` from the hash once CaseService sets it.
- Validation: ruff check and format clean; pytest 214 passed (23 new in `tests/unit/test_contract_v020.py`); all 8 CI eval gates pass; the pipeline with Track A's real `validate_correction` attaches `schedule_end S-1` and is BLOCKED by its pending rules, as intended.
- Next step: Jayanth adopts 0.2.0 in the validator/CaseService and confirms; Amulya moves evals to complete evidence with both validators side by side.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — Amulya Mohan — SHARED-01 — Verification of contract 0.2.0-draft

- Branch: `backend`.
- Status: REVIEW.
- Defects found and fixed:
  - Timestamps stored in UTC (what a database usually returns) broke the evidence gates: a note agreeing with the schedule was flagged as a conflict, note times could not be matched, and the model's `<facts>` showed 03:30-12:30 for a 09:00-18:00 shift. All failed safe (escalate/block) but would have rejected good cases. Every time is now read in `employee.timezone` (`local_zone` in `app/ai/evidence.py`).
  - `Weekday.index` shadowed `str.index`; renamed to `Weekday.number`.
  - For codes the time gate does not anchor, a model-supplied `evidence_ref` would have reached the validator unverified; it is now removed.
  - `RuleCheck` derived `outcome` from `passed is True`, so a JSON `"true"` would have failed; it now uses the same bool coercion as the field.
  - Live Qwen wrote `"note": null` on every x08 run; the schema rejected it, the repair retry pushed the case past the 8 s budget, and it escalated by timeout instead of being blocked by the time-evidence gate (safe either way). A null note is now read as empty.
- Validation (actually run): clean venv from `requirements-dev.lock` (tzdata 2026f): pytest 223 passed, ruff check and format clean, 8/8 CI eval gates; real server over HTTP (`/health` reports `0.2.0-draft`, `/assistant/query`, problem+json on bad input, no server errors); probes for UTC storage, overnight note on the next day, a US DST date, `as_of` boundary to the second, wrong evidence kind; live Qwen2.5-7B: all 6 live gates, proposal accuracy 100%, 0% repair retries, p50 5.57 s, p95 6.28 s; x08 blocked by `time_evidence` in 5/5 direct runs. The same machine ran the previous commit at p50 5.66 s, so today's higher latency (vs 4.23 s yesterday) is the machine, not this change. Pipeline with Track A's real `validate_correction`: evidence ref attached, BLOCKED by its pending rules as intended.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — C V Jayanth — A-03 + A-RULES-05 — Decisions, audit, trusted totals; contract 0.2.0 adopted

- Branch: backend (pulled Track B 1c4e895 fast-forward; no conflicts). Status REVIEW. Local only; not committed.
- A-03 (demo store): POST /exceptions/{id}/decisions and GET /exceptions/{id}/audit.
  - Each approval is one BEGIN IMMEDIATE transaction: authorize, idempotency, stale check, fresh totals,
    real validator, then decision + correction + audit, then a revision bump.
  - Failed validation is audited as APPROVAL_BLOCKED.
  - Append-only triggers and a SHA-256 audit hash chain. Only one approval per exception.
  - Rejects keep the exception open. The list endpoint shows resolved status.
  - Details: docs/RESOLUTION_API.md.
- Trusted totals: app/resolution/totals.py reads stored day totals by policy week and quarter.
  An incomplete history returns None, which gives insufficient_evidence.
  Approved corrections update that day's worked hours. The seed provisions synthetic totals and a break,
  so the demo case is approvable.
- Contract 0.2.0 adoption: outcome on every RuleCheck; evidence_ref tolerance (schedule, note via Track B's
  pure note_times, history); as_of from the server clock, excluded from the hash; open shifts are not yet missing;
  punches after as_of rejected; policy week_start and quarter_start_month. Rule version attendance-rules@0.4-draft.
- Behaviour change: missing totals now ESCALATE instead of BLOCK (as Track B requested). A duplicate-time punch is a violation.
- Validation:
  - 390 pytest passed (1 existing upstream warning); Ruff lint passed; 124 files formatted.
  - `evals.run --gates ci` 8/8 PASS on the STAND-IN validator with the mock provider.
  - Synthetic end-to-end smoke: CaseService (as_of) -> generate_proposal with the real validator and trusted totals
    -> ELIGIBLE with evidence_ref schedule_end -> approve 200 resolved -> audit DECISION_APPROVED.
    That smoke used the mock provider.
- Limits: demo SQLite store, not final migrations; only add_punch corrections; no bulk decisions or escalation persistence.
- Open: should an evidence-backed late clock-out (SCHEDULE_DEVIATION, warning) escalate rather than block?
- Next step: commit and push; Amulya swaps the real validator plus a totals fixture into evals; SHARED-02 review.

### 2026-11-18 — C V Jayanth — A-DB-PG-01 — PostgreSQL persistence

- Branch: backend; status REVIEW; local until committed. Decision: PostgreSQL (team call), built by Track A now.
- Changed:
  - ResolutionStore now runs over a backend: SqliteBackend (demo/tests) or PostgresBackend (normalized schema).
    Shared decision, audit and totals code.
  - AttendanceSettings.database_url selects PostgreSQL.
  - Optional extra `postgres` (psycopg 3) in pyproject.toml.
  - Migration runner and script; the seed script supports `--database-url`.
- Found by PostgreSQL, fixed:
  - the audit event referenced its decision before the decision row existed (FK now DEFERRABLE INITIALLY DEFERRED);
  - the seed silently kept a conflicting shift, so seeding now refuses id clashes.
- Validation:
  - 390 passed / 27 skipped without PostgreSQL; 417 passed with TEST_DATABASE_URL on local PostgreSQL 15.
  - Ruff lint and format pass; `evals.run --gates ci` 8/8 PASS (stand-in validator, mock provider).
  - PostgreSQL end-to-end smoke: seed -> list/detail -> pipeline ELIGIBLE -> approve 200 resolved -> audit,
    with the row status resolved at revision 1.
- Needs Track B: a PostgreSQL service in CI and Docker (see RESOLUTION_API.md). Until then CI skips the PostgreSQL tests.
- Next step: review with Soumya when her database work is pushed; commit and push on approval.

### 2026-11-18 — C V Jayanth — A-05, detection, A-06, adjust_punch

- Branch: backend; status REVIEW (A-06 attendance event updates still pending). Local only; not committed (held with the PostgreSQL work pending Soumya's review).
- A-05 import: app/attendance/importer.py (pure preview) and imports_router.py (POST /imports/preview, POST /imports; PostgreSQL only).
  It handles field mapping, type aliases, naive local times in the employee's timezone, DST gap/overlap refusal,
  in-file and database duplicates, deterministic ids (re-import is a no-op), manager scope, and allow_partial.
- Detection: app/rules/detection.py (work-date sessions, the same evaluate_rule_outcomes; violations only)
  and app/attendance/ingest.py (effective timecard = raw + approved corrections, deterministic exception ids,
  EXCEPTION_DETECTED audit, whole-week day totals).
- day_totals now separates evidence_final from complete. Without it, a detected missing punch could never be approved:
  the work date needs final evidence, while other days need known hours.
- A-06: POST /exceptions/bulk-decisions (1-50 items; each authorized, validated and committed independently).
- Item 7: adjust_punch for OVERLAPPING_SHIFT, SPREAD_OVER_BREACH and SCHEDULE_DEVIATION (note-evidence only, bounded move).
  Other action types are refused until their semantics are agreed (questions in TRACK_A_CONTRACT_RESPONSE.md).
- Validation:
  - 429 passed / 31 skipped without PostgreSQL; 460 passed with TEST_DATABASE_URL (local PostgreSQL 15). Ruff passes.
  - `evals.run --gates ci` 8/8 PASS (stand-in validator, mock provider).
  - The SHARED-02 path on PostgreSQL is tested end to end: import shifts and punches -> detection (exactly one MISSING_PUNCH)
    -> re-import no-op -> list/detail -> generate_proposal ELIGIBLE with derived totals -> approve -> audit -> re-detection quiet.
- Next step: review with Soumya's database work; Amulya answers the adjust/acknowledge questions and adds PostgreSQL to CI.

### 2026-11-18 — Amulya Mohan — B-05 — Evaluations on Track A's real validator with complete evidence

- Branch: `backend`.
- Status: REVIEW.
- Changed:
  - `evals/schema.py`: cases carry complete evidence by default (observed meal break punches 4 h into the shift, trusted totals via `AggregateSpec`, `as_of` the next day at 12:00); cases opt out explicitly; new `evidence` category and `rules_only` flag; `detection_details` names the unmatched work punch, not a break.
  - `evals/aggregates.py` (new): trusted `AggregateEvidence` per case, keyed by the case's own exception id; week and quarter starts from the pack (`week_start`, `quarter_start_month`); `real_validator` = Track A's `make_validator(load)`.
  - `evals/run.py`: every proposal is validated by the real rules; the stand-in judges the same recorded model outputs (replayed, no extra model calls) as a comparison column; safety gates require zero unsafe under both; accuracy gated on the real validator (`--gate-validator`); new CI gate `evidence_case_accuracy`.
  - `evals/cases/evidence.json` (new, 9 cases): totals unavailable, no break, weekly overtime (US-FED), totals for the wrong week, open shift at `as_of`, uncertified work date, short break, plus two eligible controls.
- Results (mock, CI): 9/9 gates; real and stand-in agree on all shared cases. Rebased onto Track A's 0.2.0 adoption (8ad2e15): the gap cases now require exact outcomes, and each stops on the rule it targets: e01/e04/e06 ESCALATED (`insufficient_evidence`), e02/e03/e07 BLOCKED (`violation`), e05 BLOCKED by the as_of gate, controls e08/e09 ELIGIBLE. Live Qwen2.5-7B against 8ad2e15: all 6 live gates, proposal accuracy 100% under both validators, every category 100%, 0 repair retries, p50 5.24 s, p95 5.69 s. The real rules made 0 of 6 rules-only cases eligible; the stand-in would have made 6 of 6 eligible.
- Contracts: none (uses `make_validator` and `AggregateEvidence` as published by Track A; no Track A files changed).
- Validation: ruff check and format clean; pytest 396 passed (incl. Track A's 8ad2e15); `python -m evals.run` 9/9 CI gates; live run above.
- Next step: commit, then generate the committed live report from a clean tree.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — Amulya Mohan — B-05 / SHARED-01 — CI PostgreSQL, adjust_punch evidence gate, answers to Track A

- Branch: `backend` (pulled Track A c85111c: PostgreSQL store, import/detection, bulk decisions, adjust_punch).
- Status: REVIEW.
- CI and Docker (Track A request in RESOLUTION_API.md):
  - The backend job has a `postgres:15` service with `TEST_DATABASE_URL` (a `_test` database, trust auth, CI only) and installs `.[dev,postgres]`.
  - A guard step fails the build if any PostgreSQL test is skipped.
  - `psycopg==3.3.9` and `psycopg-binary==3.3.9` are pinned in `requirements-dev.lock`.
  - `docker-compose.yml` has a `postgres` profile (PostgreSQL 15, 127.0.0.1 only, volume `postgres-data`); the API image installs the `postgres` extra; `.env.example` and LOCAL_DEVELOPMENT.md show the local setup.
- Evidence gate: `anchor_times` now handles `adjust_punch` for every code. The target must be one of the case's punches, its type is read from that punch, and only `note` refs are attached; schedule and history refs (including model-supplied ones) and times after `as_of` are refused. Other unanchored actions still have model-supplied refs removed.
- Answers: Track B section in TRACK_A_CONTRACT_RESPONSE.md (adjust_punch; semantics proposals for acknowledge, add_break, void_shift, flag_premium, suggest_schedule_swap; detection_details keys; escalate evidenced warning-level deviations).
- Finding raised: two-sided tolerance can grant unclaimed time. With the real validator, a note stating 09:05 lets an adjustment to the scheduled 09:00 become ELIGIBLE. Proposed one-sided rounding of stated times; not changed unilaterally.
- Validation: ruff check and format clean; pytest 441 passed and 31 PostgreSQL tests skipped without a database; with `TEST_DATABASE_URL` on local PostgreSQL 15.20 (compose profile), 466 passed and the guard passed, and without it the guard fails as intended; `docker compose config` valid; API image built, and `psycopg` 3.3.9 and the app import inside it; `python -m evals.run` 9/9 CI gates on Track A's c85111c validator.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — C V Jayanth — A-PROPOSE-01 — Proposal API, escalation, demo week, pay integrity

- Branch: backend (pulled Track B dcccc0c first; no conflicts). Status REVIEW.
- New: POST /exceptions/{id}/proposal runs Track B's pipeline with the real validator and trusted
  totals inside one transaction, persists the draft and its model trace (migration 0002: proposals,
  llm_traces, escalations) and audits PROPOSAL_GENERATED. It never approves.
- Escalation is now persisted: the pipeline escalates a case on its own, a manager can escalate with
  a reason, and GET /exceptions?status=escalated lists them. Status is derived resolved > escalated > open.
- GET /exceptions/{id}/timecard shows raw punches, the approved corrections applied and the resulting hours.
- Agreed with Track B and implemented: a stated time (note ref) is rounded only in the direction that
  adds no paid time (their 09:05 -> 09:00 example is now refused); an evidenced fix whose only
  remainder is a warning returns insufficient_evidence ("manager review") so it escalates, not blocks.
- Bug found by the demo seed and fixed: an unpaired clock-in absorbed every following day into one
  session, so a single missing clock-out hid the rest of the week. Regression test added.
- scripts/seed_demo_week.py provisions a synthetic week through the real import path and detection
  raises all six exception types plus one clean day.
- Validation: 490 passed with TEST_DATABASE_URL on local PostgreSQL 15 (453 passed / 36 skipped
  without it); Ruff lint and format pass; evals.run --gates ci 8/8 PASS.
  HTTP demo on PostgreSQL: 6 exceptions detected -> proposal ELIGIBLE (6/6 checks, schedule_end
  evidence, KA-8 citation) -> approve 200 resolved -> timecard 3 raw / 4 effective / 8.0 h ->
  audit DETECTED, PROPOSAL_GENERATED, DECISION_APPROVED. Mock provider: this proves the harness, not model quality.
- Limits: no attendance event push, no structured detection_details keys yet, and the correction
  types awaiting contract 0.3.0 are still refused.
- Next step: Amulya drafts 0.3.0 (add_break new_end_ts, void_shift target_punch_ids); Track A adds
  structured detection_details and the remaining action types.

### 2026-11-18 — C V Jayanth — DB-03 — Display fields from the database branch review

- Branch: backend; status REVIEW. Reviewed Soumya's `origin/database` 48b2a1a: it cannot be merged
  as it stands (old layout, SQLite/SQLModel, naive timestamps, no immutability triggers, cascade
  deletes, several contract mismatches). Details in `backend/database/docs/UPDATE.md`.
- The one real gap it exposed is fixed: migration 0003 adds `organizations`, `locations` and
  employee `full_name` / `job_title` / `pay_type`, and `GET /exceptions` now returns
  `employee_name`, so a manager sees who an exception belongs to. Display only; detection and
  validation are verified to work with every one of those columns null.
- Validation: 491 passed with PostgreSQL (454 passed / 36 skipped without it); Ruff lint and format
  pass; `evals.run --gates ci` 9/9 PASS. Demo seed re-run: six exceptions, now listed with names.
- Next step: Soumya reworks her branch onto this schema (DB-06); Track A adds structured
  `detection_details` keys.

### 2026-11-18 — Amulya Mohan — B-05 — Committed live report on Track A's real validator

- Branch: `backend`.
- Status: REVIEW.
- Changed: `backend/evals/reports/ollama-qwen2.5-7b-instruct-propose_v2-real-validator.{md,json}` generated from a clean checkout of dcccc0c; results added to `docs/MODEL_CARD.md` and CLAUDE.md. `scripts/live_check.py` now validates with Track A's `make_validator` (complete evidence: observed break, as_of, trusted in-limit totals with policy periods). The stand-in's report label now reads "comparison only".
- Results: all six live gates pass; 45 cases, proposal accuracy 100% under both validators, every category 100%, citation validity 100%, no repair retries, p50 4.78 s, p95 5.17 s. On the 6 rules-only cases the real rules made 0 eligible and the stand-in would have made 6. Live smoke check 6/6 (p50 5.0 s).
- Contracts: none.
- Validation: report run above (clean tree); live smoke check above; `live_check.py --provider mock` 6/6; ruff clean; pytest and CI eval unchanged.
- Next step: extend proposals beyond MISSING_PUNCH (SCHEDULE_DEVIATION adjust_punch, OVERLAPPING_SHIFT, SPREAD_OVER_BREACH).
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — Amulya Mohan — B-02 / B-05 — AI proposals beyond missing punches (step 2)

- Branch: `backend`.
- Status: REVIEW.
- Changed:
  - `app/ai/evidence.py`: pre-model gate for SCHEDULE_DEVIATION, SPREAD_OVER_BREACH and OVERLAPPING_SHIFT (escalate when no note states a time, or every stated time is more than `missing_punch_window_min` from all recorded work punches); stated (note) and habitual (history) times round one way only, so no paid time is added; schedule stays two-sided.
  - `app/ai/pipeline.py`: per-code `<facts>` (stated times as claims, deviation minutes, spread vs limit, overlapping sessions paired FIFO like Track A's engine, an "Allowed fix" rule); citation-id normalisation for mangled ids that unambiguously name a retrieved active clause, recorded as `citation_ids_normalised`.
  - `prompts/propose_v3.md` (new default; v2 and v1 kept); config, `.env.example` and eval CLI updated.
  - Mock provider drafts stated-time adjustments (overlaps move the earlier session's clock-out).
  - Evals: `evals/cases/adjustment.json` (12 cases, `rules_only`), expected `punch_id` checked, category `adjustment`, `detection_details` = `{"reason": ...}` for non-missing-punch codes as Track A writes it.
  - Tests: `tests/unit/test_adjustments.py` (gate, rounding, facts, prompt, end to end, citation normalisation).
- Found and fixed during the work: FIFO pairing in the overlap facts (first version dropped the second session); the mock first moved the wrong punch in an overlap, which the real validator blocked and the expected `punch_id` caught.
- Results: mock/CI 9/9 gates; live Qwen2.5-7B, 57 cases, v2 and v3 both 100% proposal accuracy with every category 100%, all six live gates, 0 repair retries (p50 5.95 s / 6.12 s). Five repeats: spread-over fix v2 4/5 vs v3 5/5, so v3 is the default. KA-11's id was mangled in 9/10 live runs before normalisation.
- Contracts: none (uses `adjust_punch` and `EvidenceRef` from 0.2.0). Answer on one-sided history rounding added to TRACK_A_CONTRACT_RESPONSE.md.
- Validation: ruff check and format clean; pytest 474 passed (44 PostgreSQL tests skip locally without `TEST_DATABASE_URL`; CI runs them); `python -m evals.run` 9/9 gates; live runs and repeats above.
- Next step: commit, then the committed live report from a clean tree.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — Amulya Mohan — Backend audit (both tracks)

- Branch: `backend`.
- Status: REVIEW. Report: `backend/docs/shared/AUDIT_2026-11-18.md`.
- Method: clean venv from the lock file (`pip check`, ruff, bandit rules); 518 tests on PostgreSQL 15 with none skipped; CI eval 9/9; a migrated and seeded PostgreSQL demo week (all six exception types detected through the real import path) driven over HTTP with 49 scripted checks, with the mock and with live Qwen2.5-7B; append-only triggers, audit hash chain and `db_maintenance verify` tested in the database; line-by-line review of auth, routers, SQL, store transactions, rule engine and totals.
- Track A findings (reported, not changed): A1 High, a 1-minute clock-out/clock-in passes the meal-break rule; A2 High, `propose` holds the global write lock (advisory lock / BEGIN IMMEDIATE) during the LLM call, and three concurrent proposals took 8.9/15.8/22.3 s; A3 Medium, `llm_traces` is keyed by the client-suppliable trace id, so reusing `X-Trace-Id` gives 500; A4 Medium, unsupported fix types block instead of escalating; A5 Medium, early arrival and late departure are flagged as deviations, contrary to KA-9/US-6; A6 Low, `effective_to` is inclusive in the engine but exclusive in the registry; A7 Low, stale API docs.
- Track B fixes: B1, the assistant requires a manager token when the attendance store is enabled; B2, HTTP providers and the Ollama embedder are shared per configuration (connection reuse, which also covers Track A's proposal route); B3, identical validator reasons are grouped. Tests: `tests/unit/test_audit_fixes.py`.
- Validation after the fixes: ruff clean; pytest 481 passed (44 PostgreSQL tests skip locally without `TEST_DATABASE_URL`; 518 earlier with it); eval 9/9; HTTP walk-through 47/49, where the two failures are A3 and a harness typo (the import check passed with the correct column in a separate probe).
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — Amulya Mohan (Track B, at the owner's request) — Track A audit fixes A1-A7

- Branch: `backend`.
- Status: REVIEW (Track A to review; A5 to confirm intent).
- Changed (Track A modules, edited at the repository owner's request; each change carries its audit id):
  - `app/rules/engine.py`: A1, a gap between work sessions counts as rest only when it lasts `rest_minutes`; A5, only a late arrival or an early departure is a schedule deviation; A6, `effective_to` is exclusive.
  - `app/rules/validator.py`: A4, unsupported fix types are `insufficient_evidence` (escalate).
  - `app/resolution/store.py`: A2, `propose` reads, runs the pipeline with no transaction or lock held, then re-checks the evidence in a short write (409 if it changed); A3, trace rows are keyed `<trace id>:<proposal id>`.
  - `docs/RESOLUTION_API.md`, `docs/ATTENDANCE_API.md`: A7.
  - Tests: new `tests/unit/test_audit_track_a.py` and `tests/integration/test_audit_store.py` (the A2/A3 tests fail on the old code, confirmed); two Track A tests updated for A5.
- Track B: prompt v3 rule 5 scoped to recorded punches (a live regression on c10 found during verification); eval cases d02 and d11 replaced and d13 added for the corrected rules.
- Validation: pytest 550 passed on PostgreSQL 15 (none skipped); ruff clean; eval 9/9; Docker stack with live Qwen: HTTP walk-through 49/49, 0 server errors, audit chain valid; a decision during model calls took 0.57 s; full live eval 100% in every category, 0 unsafe.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — C V Jayanth — A-AUDIT-01 — Review of Track B's audit fixes; structured details; employee notes

- Branch: backend (fast-forwarded to b2c7a86 first). Status REVIEW. Local until committed.
- Reviewed audit changes A1-A6 in engine.py, validator.py and store.py against the code and the policy text.
  All agreed. A5 follows KA-9 / US-6; the earlier two-sided schedule check was a Track A error.
- Structured `detection_details` (app/rules/explain.py): every exception stores scalar facts next to `reason`,
  using the keys Track B listed plus `limit_kind` for OVERTIME_RISK.
- Employee notes: `POST /imports` accepts `kind: "notes"`; notes attach to an open or escalated exception when
  written on its work date or the day after; attaching changes evidence_version and is audited as EVIDENCE_ATTACHED;
  import plus attach is one transaction; a note imported early is attached when detection runs. A first 7-day window
  attached Friday's note to Tuesday's exception (seen in the seed output) and was tightened to 2 days.
- `seed_demo_week.py` imports four notes through that path; each lands on exactly one exception.
- Validation: 580 passed with TEST_DATABASE_URL on local PostgreSQL 15, 527 passed / 53 skipped without it; Ruff
  lint and format pass; `evals.run --gates ci` 9/9 PASS (the mock provider; this proves the harness, not model quality).
  The AI flows that read the notes were not run against a live model here.
- Open: "unscheduled shift" as a schedule deviation needs a signal that schedules are complete; contract 0.3.0 review.

### 2026-11-18 — Amulya Mohan — Live verification of Track A 090bbdd; two fixes

- Branch: `backend` (pulled 090bbdd: structured detection details, note import, demo notes).
- Status: REVIEW.
- Changed:
  - `app/ai/pipeline.py` (Track B): the case JSON shows timestamps in the employee's local zone. On PostgreSQL (UTC) the model copied `+00:00` onto local wall times, so every adjustment was blocked live.
  - `app/ai/evidence.py` (Track B): a stated time equal to a recorded punch does not count as a correction (the double-tap note now escalates before the model).
  - `app/resolution/store.py` (Track A, at the owner's request): approval and the timecard read share `apply_actions`; approving an `adjust_punch` returned 500 and would have double-counted day totals.
  - Tests: `test_case_json_shows_local_times_when_storage_is_utc`, `test_utc_stored_case_end_to_end_with_mock`, `test_stated_times_that_equal_recorded_punches_escalate`, `test_approving_an_adjustment_applies_it_once` (SQLite and PostgreSQL; fails on the old code).
- Validation: pytest 585 passed on PostgreSQL 15 (none skipped); ruff clean; eval 9/9; Docker stack with live Qwen: demo story end to end (missing punch approved, then the late arrival eligible and approved to the stated 09:05, net 7.92 h), HTTP walk-through 49/49, 0 server errors; full live eval 100% in every category, 0 unsafe, p50 4.58 s.
- Answered in TRACK_A_CONTRACT_RESPONSE.md: unscheduled shift stays insufficient_evidence until a "roster final" signal exists (proposal for 0.3.0); two questions for Track A (overtime-only remainder after an evidenced fix; timecard time zone).
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — Amulya Mohan — Settle open questions; verify end to end before merging to main

- Branch: `backend`.
- Status: REVIEW, then merge into `main`.
- Changed (Track A modules at the owner's request): `app/rules/validator.py`, so an evidenced fix leaving only warning-severity violations (SCHEDULE_DEVIATION and/or OVERTIME_RISK) is escalated; `app/resolution/store.py` and `router.py`, so the timecard is in the employee's zone with a `timezone` field. Tests updated and added; eval e03 now expects ESCALATED.
- Decided: an unscheduled shift stays `insufficient_evidence` until a roster-final signal (0.3.0).
- Validation: the Windows host now blocks the psycopg DLL (Application Control; settings not changed), so tests ran in a Linux `python:3.12-slim` container on the compose network: 590 passed on PostgreSQL 15 (none skipped), ruff clean, eval 9/9. Docker stack (API image, PostgreSQL, Ollama on the GPU), fresh demo week seeded from a container: demo story end to end (missing punch approved, then the late arrival eligible and approved to the stated 09:05), and the spread-over now escalates for review; HTTP walk-through 49/49, 76 requests, 0 server errors; full live eval (in a container) 100% in every category, 0 unsafe, 0 repair retries, p50 4.44 s.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — C V Jayanth — A-AUDIT-02 — Self-audit of the code written after Track B's audit

- Branch: backend. Status REVIEW. Full findings, reproductions and what was checked and fine:
  `backend/docs/AUDIT_TRACK_A_2026-11-18.md`.
- Fixed (each reproduced by a failing test first): approving an `adjust_punch` returned 500 (three places re-implemented
  "apply corrections"; now one shared `app/resolution/apply.py`); exceptions never cleared and a cleared one could never
  return (now dismissed/reopened, audited); a retry after a failed detection detected nothing; hostile CSV/JSON caused
  500s (cell size, nesting depth, huge integers, year overflow, NUL bytes including the JSON escape, break length
  overflowing a 32-bit column); one write transaction per import stalled every approval (now one per employee).
- Measured, not assumed: detection costs about 5 ms per employee (120 employees, 0.58 s).
- Checked and fine: 6,000-day fuzz of detect/explain/grouping/apply (no crash, no stray detail key); the concurrent
  approval race; cross-employee evidence; no HTML or eval sinks in the frontend.
- Validation: 614 passed with TEST_DATABASE_URL on local PostgreSQL 15, 551 passed / 63 skipped without it; Ruff lint and
  format pass.
- Found while writing the fix, not yet fixed: the frontend audit CSV export has formula injection (separate commit, branch
  `frontend`).
- Added to the audit above (found when checking how the UI reads times): the API's timestamps depended on the database
  session's timezone (`03:30Z` from a UTC server vs `09:00+05:30` locally), which would have broken the Docker demo's
  timeline. Case times are now always in the employee's timezone; `evidence_version` is unchanged. 615 passed with Postgres.

### 2026-11-18 — Audit follow-up — Effective workday consistency

- PostgreSQL timecards and approval totals now reuse detection's corrected employee punches and work-date grouping, including adjustments that bring in unlinked punches.
- Approval returns a conflict if the effective workday differs from the exception's linked punch IDs or timestamps. The manager must review the updated timecard before a correction can proceed.
- Timecard raw evidence and correction history retain their exception scope. The effective punches and net hours describe the employee's workday. SQLite retains its snapshot behavior.
- Added a PostgreSQL regression for a punch adjusted into the workday from outside the exception's evidence.
- Publication: local changes in the audit fix worktree.

### 2026-11-18 — Audit follow-up — Multiple exceptions on one workday

- PostgreSQL open and escalated cases now use the effective workday for evidence snapshots, proposal validation and approval. A correction on a sibling exception changes that snapshot's evidence version, even when its exception revision stays the same.
- Replaced the linked-punch equality guard. An outdated request still conflicts, and a refreshed request reaches the deterministic rules. Historical case and timecard raw evidence remain scoped to the exception.
- Added a PostgreSQL regression for a clock-out added by a correction on another exception.

### 2026-11-18 — Amulya Mohan — Hand-in: merged to main, final docs

- Branch: `backend`, fast-forwarded to `main` 34c2506 (PR #12 from Track A, then PR #13 from `backend`).
- Status: DONE for the deadline; future work listed in CLAUDE.md, shared TASKS.md and MODEL_CARD.md.
- Validation on the merged code: CI on `main` green (639 tests on PostgreSQL, none skipped); Docker stack with live Qwen2.5-7B: demo story end to end, HTTP walk-through 49/49, 0 server errors; full live eval 100% in every category, 0 unsafe, p50 4.45 s.
- Decision: contract 0.3.0 is out of scope for the deadline. Unsupported fix types escalate to the manager.
- Publication: committed and pushed to `backend` (authorised by the owner).

### 2026-11-18 — Overtime warning carry-over regression

- Reproduced an approval that increased projected weekly hours from 49 to 50 against a 48-hour limit.
- The validator keeps an existing overtime warning blocking if a correction increases net worked hours. Corrections that leave hours unchanged or reduce them retain the existing carry-over behavior.
