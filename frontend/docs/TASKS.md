# Frontend tasks

Claim an owner before starting. Statuses: TODO, IN PROGRESS, BLOCKED, REVIEW, DONE.
Shared dependencies refer to backend/docs/shared/TASKS.md; do not duplicate their status here.

| ID | Task | Owner | Status | Depends on | Acceptance |
| --- | --- | --- | --- | --- | --- |
| FE-01 | API contract and synthetic fixtures | Chaithanya | REVIEW | SHARED-01 | Agreed shapes; labeled fixture boundary |
| FE-02 | Inbox and resolution panel | Chaithanya | REVIEW | FE-01 | Evidence, citations, validation and all screen states |
| FE-03 | Decision and audit flow | Chaithanya | IN PROGRESS | FE-02, backend decision API | Server-confirmed approval/edit/reject; stale and denied states |
| FE-04 | Import preview and language interaction | Chaithanya | TODO | FE-03, backend imports/intents | Invalid rows shown; language preserves canonical fields |
| FE-05 | Accessibility and end-to-end review | Chaithanya | TODO | FE-04 | Keyboard, narrow layout, and full workflow verified |
