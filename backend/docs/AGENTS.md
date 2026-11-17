# Shared instructions for coding agents

All file paths below are relative to the repository root, not this directory.

Read `backend/docs/shared/TEAM_RULES.md`, `backend/docs/shared/TASKS.md`, and the latest entries in `backend/docs/UPDATE.md` before making changes. Follow the user's current instructions if they conflict with these files.

## Before work

1. Check the current branch, working tree, and Git author identity. Preserve existing user changes.
2. Fetch remote branches when network access is available. Read teammates' published updates before claiming work. Do not silently switch branches or merge unrelated work.
3. Select a task in `backend/docs/TASKS.md` (linked to `backend/docs/shared/TASKS.md`), assign it to the current developer, and mark it in progress. If another developer owns it, coordinate before changing that scope.
4. Read the relevant contracts and establish dependencies. Do not invent a teammate's interface or claim their unfinished implementation is available.
5. For a new teammate session, ask for their name and track if these are unknown. Never reuse another developer's commit identity.

## During work

- Stay within the claimed task. Shared contract or core changes require a reviewable proposal for the other developer.
- Keep changes small and integration-ready. Use mock boundaries when dependent modules are unfinished.
- Follow the product invariants in `backend/docs/shared/TEAM_RULES.md`.
- Run checks appropriate to the change. Distinguish checks actually run from proposed checks.
- Never commit secrets, real employee data, local databases, or model credentials.

## Before handing off or committing

1. Update `backend/docs/TASKS.md` and any affected shared milestone in `backend/docs/shared/TASKS.md`.
2. Append a dated entry to `backend/docs/UPDATE.md` using its template. Never rewrite another person's history.
3. Include implementation, tests, task status, and update log in the same commit when committing.
4. Report the branch, changed files, validation, blockers, and next step. State explicitly if changes remain local.
5. Commit or push only when authorized by the user's task. Do not auto-merge or push to a teammate's branch.

An update log is coordination, not a lock or a real-time notification service. A teammate sees changes only after they are published and fetched. Reconcile simultaneous task claims before proceeding.

## Backend implementation boundaries

- Read backend/docs/TASKS.md for track A/B ownership. Use `backend` for backend implementation.
- Preserve FastAPI/Pydantic contracts and module boundaries; agree SHARED-01 before adding domain APIs.
- Track A owns attendance, rules, resolution and audit; track B owns policy, retrieval, providers and language.
- Coordinate schema/migration changes with backend/database/docs/AGENTS.md. The database team owns migration ordering; track A is the backend liaison.
- Enforce authorization and employee scope server-side, not through UI hiding or a trusted client-supplied role alone.
- Detection is deterministic. Both AI suggestions and manager edits reuse the same correction validator.
- Recheck policy/evidence versions and authorization at approval. Make correction and audit persistence atomic and retry-safe.
- LLMs cannot write corrections. Validate action types, output schema, retrieved citation membership and evidence completeness.
- Missing evidence must yield escalation, including when no citation exists. Confidence cannot override failed checks.
- Keep policy thresholds in versioned configuration. Never adjust punches merely to conceal a genuine violation.
- Keep provider access behind adapters; mock mode must be explicit. Timeouts and unavailable retrieval preserve manual review.
- Agree error contracts and trace propagation with frontend. Do not expose provider keys, sensitive notes or raw traces indiscriminately.
- Run `.venv/bin/python -m pytest backend/tests` and `.venv/bin/python -m ruff check backend` for relevant changes.
- Add meaningful tests for boundaries, unauthorized access, duplicate decisions, stale evidence and failure behavior as implemented.
- Do not claim future endpoints, models, providers, Docker or CI already work.
