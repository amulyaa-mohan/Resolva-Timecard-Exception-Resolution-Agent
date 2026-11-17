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
