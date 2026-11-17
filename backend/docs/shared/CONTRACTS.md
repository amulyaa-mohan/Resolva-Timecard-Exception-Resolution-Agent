# Cross-team contract coordination

Status: proposed interfaces only; SHARED-01 is not yet agreed.
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
