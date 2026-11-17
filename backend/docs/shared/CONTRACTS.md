# Cross-team contract coordination

Status: SHARED-01 draft `0.1.0-draft` exists in `backend/app/core/contracts.py` (proposed by Track B; not yet agreed).
Open decisions and how Track A plugs in: `backend/docs/shared/TRACK_B_INTEGRATION.md`.
Actual running API: GET /health. Do not infer other routes from planning documents.

Before implementing a shared boundary, record:
- Task ID, proposing owner and affected teams.
- Request/response fields, types, nullability, IDs and timezone semantics.
- Permissions, validation, errors, retry/idempotency and evidence-version behavior.
- Database revision or frontend fixture affected.
- Reviewer decisions and the final contract location.

Backend OpenAPI will be the HTTP contract once reviewed endpoints exist.
Frontend types should be generated from that contract; database revisions must match agreed backend models.
Interface proposals in TEAM_RULES.md remain proposals until owners explicitly agree.
Review does not happen automatically because an agent wrote a document.

## Frontend alignment notes (2026-11-17, Track B)

Read-only comparison of `origin/frontend:frontend/src/types/contracts.ts` (FE-01/FE-02) with the
backend draft `backend/app/core/contracts.py`. The frontend types are UI view models for an HTTP
API that does not exist yet, so these are items to settle when Track A defines the routes and the
OpenAPI-generated types replace hand-written ones:

- `ProposedAction` has no `punch_type`; the backend requires it for `add_punch` (clock-in vs clock-out).
- `evidence_version` is a `number` in the frontend and an opaque `string` hash in the backend.
- The frontend has `validator_passed: boolean`; the pipeline returns `status`
  (`eligible`/`blocked`/`escalated`), `reasons`, and per-gate `gate_checks`, which is what the
  validator checklist and escalation views need.
- `RuleOutcome {rule, passed, detail}` vs backend `RuleCheck {code, passed, reason}`.
- `PolicyPack` is flat; the backend `PolicySnapshot` nests `rules` and adds `status`, effective dates,
  `missing_punch_window_min` and `content_hash`.
- `Punch.source` lacks `import`; ids are `id` in the frontend vs `punch_id` / `shift_id` in the backend.

## Assistant endpoint (B-04, Track B)

`POST /assistant/query` with `{"text": string (1-500 chars)}` returns `{language: "en"|"hi"|"kn",
method: "rules"|"llm"|"none", intent: Intent, query: ExceptionQuery | null, message: string,
model_id: string | null}`. See `backend/app/language/`. The frontend can call it now; results come
from Track A's exception list once it accepts the `ExceptionQuery` filters.
