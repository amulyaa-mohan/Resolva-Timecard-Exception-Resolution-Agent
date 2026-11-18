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

### 2026-11-18 — Soumya — FE-09 (FE-07) — Phase 1: P0 Exception Review & Escalations UI/UX Improvements

- Branch and status: frontend; REVIEW.
- Changed files and behavior:
  - `frontend/src/components/ResolutionPanel.tsx`:
    - Replaced clipped action button layout with wrapping flex action bar; ensured "Draft with AI" and "Re-check evidence" are always fully visible.
    - Restructured exception information hierarchy: human-readable exception title (`getHumanExceptionTitle`), employee name, and work date placed prominently at top.
    - Moved technical IDs, prompt/model hashes, canonical codes, and raw source records into an expandable `<details>` section with 1-click clipboard copy buttons.
    - Implemented 7 distinct proposal & readiness states (`no_draft`, `generating`, `eligible`, `blocked`, `escalated`, `stale`, `resolved`) with clear semantic badges, descriptions, and explicit disabled reasons on the approval button.
    - Provided empty state handling distinguishing between system-wide empty escalations vs. filter-excluded results.
  - `frontend/src/components/PunchTimeline.tsx`:
    - Fixed overlapping event markers and labels by implementing dynamic tier staggering (tier 0 vs tier 1 with connector stems) for events occurring within 40 minutes of each other.
    - Computed dynamic time window based on actual punches and schedules, displaying actual hours and employee timezone on the axis.
    - Added keyboard navigation focusability (`tabIndex={0}`) on timeline pins with live tooltips.
    - Added an accessible chronological event details table for screen readers and keyboard users.
  - `frontend/src/main.tsx`:
    - Fixed stale-selection bug: selection automatically reconciles whenever tabs or filters change; empty Escalations tab clears the detail panel with no residual inbox selection or decision controls.
    - Added table empty state distinction ("No escalations" when none exist vs "No cases match these filters" with a "Clear Filters" button).
    - Hardened keyboard shortcuts: `A`, `E`, `R` validate against currently visible results and are disabled when no item is selected or visible.
    - Enhanced KPI strip with an explicit description of Pay-Period Readiness.
    - Displayed human-readable exception types and concise summaries in table rows.
  - `frontend/src/styles.css`:
    - Added responsive styles preventing horizontal scrolling on desktop, tablet, mobile, and 200% zoom.
    - Added visible `:focus-visible` accessibility focus rings across buttons, inputs, summaries, and timeline pins.
- Contracts and cross-team dependencies: No backend or database schema modifications; preserved all existing live/synthetic API boundaries.
- Validation:
  - Executed `npm --prefix frontend run build`: passed with 0 errors.
  - Executed `git diff --check`: passed with 0 errors.
  - Executed `node scratch/verify_phase1.mjs`: verified selection reconciliation, empty escalations handling, 7 proposal states, and timeline marker staggering.
- Blockers and next step: Phase 1 complete. Awaiting review before starting Phase 2.
- Publication: local only.

## 2026-11-18 — Final frontend audit

- Favicon: added an inline SVG icon in `index.html`; the browser's automatic `/favicon.ico` request was returning 404.
- API: the proposal decision path now encodes the proposal ID, matching the other endpoints.
- Verified at 375px, 768px and 1024px: no page-level horizontal overflow on any tab. Wide tables scroll inside their own boxes.
- Verified: Policies and Kiosk screens show no untranslated sentences in Hindi.
- Checks: `tsc --noEmit` and `vite build` pass.
