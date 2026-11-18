# Frontend tasks

Claim an owner before starting. Statuses: TODO, IN PROGRESS, BLOCKED, REVIEW, DONE.
Shared dependencies refer to backend/docs/shared/TASKS.md; do not duplicate their status here.

| ID | Task | Owner | Status | Depends on | Acceptance |
| --- | --- | --- | --- | --- | --- |
| FE-01 | API contract and synthetic fixtures | Chaithanya | DONE | SHARED-01 | Agreed shapes; labeled fixture boundary |
| FE-02 | Inbox and resolution panel | Chaithanya | DONE | FE-01 | Evidence, citations, validation and all screen states |
| FE-03 | Decision and audit flow | Chaithanya | REVIEW | FE-02, backend decision API | Server-confirmed approval/edit/reject; stale and denied states |
| FE-04 | Import preview and language interaction | Chaithanya | REVIEW | FE-03, backend imports/intents | Invalid rows shown; language preserves canonical fields |
| FE-05 | Accessibility and end-to-end review | Chaithanya | REVIEW | FE-04 | Keyboard, narrow layout, and full workflow verified |
| FE-06 | Adapt and Integrate Resolva Login | Soumya | REVIEW | FE-05 | Login screen initial state, demo validation, remember email, sign-out |
| FE-07 | Phase 1 P0 Exception Review & Escalations UI/UX | Soumya | REVIEW | FE-06 | Stale selection fix, non-overlapping timeline, proposal states, responsive layout |
| FE-08 | Policies & Settings UX and persistence | Soumya | REVIEW | FE-07 | Settings controls, local persistence, validation, tests and Hindi translations |
| FE-09 | Align dropdown chevrons | C V Jayanth | REVIEW | — | Inset chevrons with a native fallback in forced colors |
| FE-10 | Hindi UI and consistent navigation layout | C V Jayanth | REVIEW | — | English/Hindi picker, shared localization and responsive header |
| FE-11 | Wire the UI to the real backend | C V Jayanth | REVIEW | FE-02, backend A-03 | Verified in a browser against PostgreSQL: token sign-in, real list/detail, draft, approve, reject, escalate, audit; a failed write is never shown as success |
| FE-12 | Import and Kiosk on the real backend; remove fabricated exceptions | C V Jayanth | REVIEW | FE-11 | Verified in a browser against PostgreSQL; no invented proposals, checks or audit events remain |