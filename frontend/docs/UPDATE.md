# Frontend updates

Append entries; preserve other developers' history. Use repository-relative paths.

## Entry template

### YYYY-MM-DD — Developer — Task ID — Summary

- Branch and status:
- Changed files and behavior:
- Contracts and cross-team dependencies:
- Validation: actual commands and outcomes; state what was not tested.
- Blockers and next step:
- Publication: local only / branch and commit / PR.

## Updates

### 2026-11-17 — C V Jayanth — COORD-04 — Area agent guidance

- Branch and status: backend; REVIEW (shared documentation preparation).
- Changed: added frontend area discovery pointer, detailed rules, task tracker and update log.
- Contracts: no business contracts finalized; read docs/CONTRACTS.md before integration.
- Validation: documentation paths and whitespace checked; no application behavior changed.
- Next step: teammates claim tasks and agree shared contracts.
- Publication: local only; these files are not yet available in remote clones.

### 2026-11-17 — C V Jayanth — COORD-05 — Two-folder repository layout

- Branch: main; status REVIEW.
- Changed: consolidated database, policies, prompts, fixtures, evaluations and scripts under backend; shared guides now backend/docs/shared. Frontend remains self-contained. Root keeps README, agent routing and Git ignore rules.
- Configuration: backend/.env.example and backend/.env are now the backend configuration paths, resolved independently of launch directory.
- Validation: backend smoke test passed (one upstream deprecation warning); Ruff passed; TypeScript/Vite build passed; active instruction paths and whitespace checked.
- History: earlier update entries retain their original paths as historical records.
- Next step: teammates bring the main reorganization into their working branches before new work.
- Publication: user authorized direct commit and push to main; team branches are not changed by this operation.

### 2026-11-17 — Chaithanya — FE-01, FE-02 — Synthetic contracts, Exception Inbox, and Resolution Panel

- Branch and status: frontend; REVIEW (ready for teammate review; awaiting SHARED-01 backend endpoints for live API wiring).
- Changed files and behavior:
  - `frontend/src/types/contracts.ts`: Defined typed contracts for `ExceptionItem`, `LLMProposal`, `ProposedAction`, `Citation`, `RuleOutcome`, `AuditEvent`, `PolicyPack`, and `Role`.
  - `frontend/src/lib/fixtures.ts`: Added labeled synthetic fixtures across `IN-KA@2025.1`, `IN-KA@2025.2-proposed`, and `US-FED+CA@2025.1` covering `MISSING_PUNCH`, `SPREAD_OVER_BREACH` (blocked/escalated), `MEAL_BREAK_BREACH`, prompt-injection resistance on `OVERTIME_RISK`, and missing-schedule escalation.
  - `frontend/src/lib/api.ts`: Added replaceable API boundary (`checkBackendHealth`, `loadInitialData`, `previewManualEditValidation`, `buildAuditRecord`).
  - `frontend/src/components/PunchTimeline.tsx` & `ResolutionPanel.tsx`: Built 24-hour shift/punch timeline, before/after hours diff, violet-labeled AI draft rationale with citations, 6-rule validator checklist, role-based read-only guard, and live manual edit re-validation.
  - `frontend/src/features/SecondaryViews.tsx`, `frontend/src/main.tsx`, `frontend/src/styles.css`: Built Exception Inbox with KPI strip, filters, bulk approve, `J`/`K`/`A` keyboard shortcuts, Escalations view, append-only Audit Trail with CSV export, Kiosk Punch Simulator, and Policy/AI kill-switch settings.
- Contracts and cross-team dependencies: Uses `/api/health` check; remaining endpoints use labeled synthetic fixtures until `SHARED-01` is frozen by backend owners.
- Validation: `npm --prefix frontend run build` (`tsc --noEmit && vite build`) passed with 0 errors; inspected desktop and narrow layouts in browser.
- Blockers and next step: Awaiting `SHARED-01` OpenAPI schema from backend to swap `frontend/src/lib/api.ts` from synthetic fixtures to live endpoints (`FE-03`).
- Publication: Pushed to `origin/frontend`.

### 2026-11-17 (Late) - Chaithanya - FE-03, FE-04, FE-05 & Root README.md (D1)
- Status: frontend -> main; REVIEW / DONE (stale 409 guard, CSV import preview, EN/KN/HI switcher, E/R/Esc shortcuts, Playwright E2E spec, and README.md complete).
- Validation: `npm --prefix frontend run build` passed with 0 errors.

### 2026-11-18 — Soumya — FE-06 — Login screen adaptation and dashboard integration

- Branch and status: frontend; REVIEW.
- Changed files and behavior:
  - `frontend/src/components/LoginScreen.tsx`: Created reusable, accessible LoginScreen component featuring demo access badge/notice, email validation (format, required), password validation (required, 6+ character minimum for demo), show/hide password toggle button, Remember Me capability (persisting strictly email in localStorage), honest demo-mode Forgot Password advisory banner, and quick autofill demo presets for Priya Menon (Manager), Suresh Kumar (Compliance), and Anita Roy (Payroll Admin).
  - `frontend/src/login.css`: Created scoped styles with `.login-` prefix adhering to Resolva enterprise theme tokens (indigo accents, neutral surfaces, responsive layouts for desktop and mobile).
  - `frontend/src/main.tsx`: Added minimal authentication state (`isAuthenticated`, `currentUserEmail`), initialized Resolva to display the LoginScreen first, conditionally rendered the existing dashboard upon successful demo login, guarded keyboard shortcut handlers when unauthenticated, and added a Sign Out button to the topbar header returning the user to the login screen while preserving all existing dashboard hooks, tabs, and exception resolution state.
  - `frontend/e2e/approve.spec.ts`: Updated Playwright E2E spec to incorporate initial login using demo credentials prior to verifying exception approval and audit trail.
  - `frontend/docs/TASKS.md` & `frontend/docs/UPDATE.md`: Registered and documented FE-06 task and progress logs.
- Contracts and cross-team dependencies: No backend or database schema modifications; authentication is explicitly labeled as demo access for team evaluation without requiring external SSO/IdP services.
- Validation:
  - Executed `npm --prefix frontend run build` (`tsc --noEmit && vite build`): passed with 0 errors.
  - Verified logic with standalone unit test suite: email format validation, 6+ character password minimum, Remember Me storing only email (never password) in localStorage, removal on uncheck, and password toggle state.
  - Verified that all existing dashboard tabs (Exception Inbox, Escalations, Import Preview, Audit Trail, Kiosk Simulator, Policies & Settings), KPI cards, and resolution actions remain fully intact.
- Blockers and next step: Ready for teammate review; future task can wire production auth provider if live authentication backend is introduced.
- Publication: local only.

### 2026-11-18 — C V Jayanth — FE-07 — Dropdown chevron spacing

- Inset and centered chevrons on single-select controls. Preserved native select interaction and restored the native indicator in forced colors.
- Validation: TypeScript/Vite production build and Git whitespace check passed.

### 2026-11-18 — C V Jayanth — FE-08 — Hindi UI and shared header layout

- Removed Kannada from the frontend language picker. Hindi applies across page controls and representative demo labels, with a persisted preference and document language.
- Both languages use the same responsive header grid. Name, identifier, and original evidence values are preserved.
- Validation: TypeScript and Vite production build passed. Git whitespace checked before commit. Browser breakpoint and native-speaker review pending.
