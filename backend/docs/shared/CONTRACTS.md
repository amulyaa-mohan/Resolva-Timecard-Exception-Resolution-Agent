# Cross-team contract coordination

Status: SHARED-01 draft `0.2.0-draft` in `backend/app/core/contracts.py` (Track B implemented the
changes agreed in TRACK_A_CONTRACT_RESPONSE.md and Track B's reply; not frozen). Changes from 0.1.0:
`RuleCheck.outcome`, `EvidenceRef` / `ProposedAction.evidence_ref`, `PolicyRules.evidence_tolerance_min`,
`week_start`, `quarter_start_month`, and `CaseContext.as_of`. Details: TRACK_B_INTEGRATION.md 5a.
Frontend `contracts.ts` does not have these fields yet; update it when the contract is frozen.
Open decisions and how Track A plugs in: `backend/docs/shared/TRACK_B_INTEGRATION.md`.
Running APIs include GET /health, POST /assistant/query, and optional authenticated GET /exceptions and GET /exceptions/{exception_id}. Decision endpoints remain pending.

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

## A-START-01 — Attendance domain draft for review

Owner: C V Jayanth. Reviewers: policy/AI teammate and database owner (pending).
Implementation: backend/app/attendance/contracts.py and backend/app/rules/missing_punch.py.
These are immutable Pydantic domain DTOs, not ORM models or published HTTP schemas.
The fixture backend/data/fixtures/missing_punch_overnight.json is synthetic.

- Employee includes manager/location IDs and a validated IANA timezone.
- ScheduledShift contains aware start/end timestamps; end must follow start.
- Punch carries a stable ID, employee, aware timestamp, event type and source event identity.
- AttendanceCase contains the complete shift-scoped evidence, as-of time and opaque evidence version.
- Case construction rejects cross-employee records, duplicate IDs/source events and future events.
- Caller supplies policy closing_grace; negative values fail. No policy thresholds are hard-coded.
- Detection waits through scheduled end plus grace before flagging a trailing clock-in.
- No punches is not interpreted as a missing punch; attendance absence needs separate handling.
- Equal-time work punches raise an ambiguity error. Break pairing is not implemented here.
- validate_added_punch reparses a copied context and invokes the same detector, preserving originals.
- PairingValidation always has approval_eligible=false: no persistence, authorization, evidence verification or full six-rule validator exists yet.
- No database migrations or domain API routes are added. SHARED-01 remains pending actual teammate agreement.

Next decisions: ingestion window/shift assignment, typed ambiguity/escalation results, policy snapshot shape, and persistence interfaces.

## Track A response and integration boundary

See TRACK_A_CONTRACT_RESPONSE.md for all ten decisions and additional draft issues.
Track A adapts core/contracts.py without changing its version. CaseService and the partial validator are implemented; production persistence/authentication remain pending.

## A-RULES-02 — Aggregate evidence proposal

See backend/docs/RULE_ENGINE.md for the internal AggregateEvidence draft, scope and trusted-source requirements.
All six closed-context checks exist; the three-argument CorrectionValidator remains compatible and fails closed without complete aggregate inputs.
No shared contracts.py or Track B modules were changed. Agreement is still needed on aggregate provenance, week/quarter boundaries, evaluation time, action targets and richer insufficient-evidence outcomes.

## A-READ-API-01 — Read-only attendance endpoint draft

See backend/docs/ATTENDANCE_API.md for filters, pagination, errors and setup.
Track A adds a router in app/attendance/router.py and registers it in main.py.
Manager tokens are server-provisioned and expiring; persisted employee assignments scope reads.
Query parameter names match Track B ExceptionQuery. Shared core/contracts.py remains unchanged.
Attendance config is independent ATTENDANCE_* settings; no Track B provider/language implementation changed.
These are demo snapshot APIs; final normalized persistence, production identity and decision writes remain pending.
