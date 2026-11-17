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
