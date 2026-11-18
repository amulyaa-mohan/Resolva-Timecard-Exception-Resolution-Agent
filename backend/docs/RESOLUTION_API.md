# Decisions, corrections and audit (A-03)

Track A. Code: `backend/app/resolution/` (store, totals loader, routes) and `backend/app/audit/events.py`.
Storage: PostgreSQL when `ATTENDANCE_DATABASE_URL` is set (schema in `backend/database/migrations`), otherwise the demo SQLite file.
The same `ResolutionStore` logic runs on both (tests run the API suite against each).
Enable it the same way as the read API (see ATTENDANCE_API.md); the seed script also provisions day totals.

## Endpoints

| Method | Path | Result |
| --- | --- | --- |
| POST | `/exceptions/{id}/decisions` | Approve or reject; 200 with `DecisionResult` |
| GET | `/exceptions/{id}/audit` | Append-only audit events for an assigned exception |

Identity comes only from the bearer token; reads and writes are limited to the manager's assigned employees.
Unknown and unassigned ids both return 404. No role header is trusted.

Request body (`DecisionRequest`, unknown fields rejected):

```json
{
  "decision": "approve",
  "actions": [{"type": "add_punch", "punch_type": "out", "new_ts": "2026-11-17T18:00:00+05:30",
               "evidence_ref": {"kind": "schedule_end", "id": "S-DEMO-1"}}],
  "source": "ai_proposal",
  "evidence_version": "sha256:...",
  "idempotency_key": "client-generated, 8-128 chars",
  "reason": ""
}
```

- `approve` needs the actions being approved; `reject` carries none.
- A reason is required to reject, or when `source` is `manager_edit` (the manager changed the proposal).
- `evidence_version` must be the version the manager reviewed (from `GET /exceptions/{id}`).

Errors use the shared RFC 7807 problem+json format:

| Status | When | Body |
| --- | --- | --- |
| 409 | Evidence changed since review | `title: "Stale evidence"`, `errors[0].current_evidence_version` |
| 409 | Already resolved, or idempotency key reused with a different body | `title: "Decision conflict"` |
| 422 | Correction fails deterministic validation | `title: "Validation failed"`, `errors` = the six RuleChecks with `outcome` |
| 422 | Malformed request | `errors` = field errors |

## What one approval does (single `BEGIN IMMEDIATE` transaction)

1. Load the case for this manager and set `as_of` from the server clock.
2. Same idempotency key and same body: return the stored result with `replayed: true`.
3. Reject if `evidence_version` is stale or an approval already exists.
4. Resolve the policy, read weekly/quarterly totals fresh (`load_aggregates`), and run the real validator.
5. On failure: append an `APPROVAL_BLOCKED` audit event (actor `system`), commit it, return 422.
6. On success: insert the decision, the correction (actions as approved) and a `DECISION_APPROVED` event.
   The event records the evidence version, policy, rule version, checks and the totals used (with periods and as-of).
   Then bump the correction revision, so every older proposal becomes stale, and update the work date's day total.

Any error rolls back the whole transaction. Raw punches (`evidence_json`) are never modified.
A partial unique index allows only one approval per exception. Concurrent writers are serialized by SQLite.
Rejecting records a decision plus `DECISION_REJECTED` and leaves the exception open.

Append-only: triggers abort UPDATE and DELETE on `decisions`, `corrections` and `audit_events`.
Audit events form a SHA-256 hash chain; `verify_chain` detects out-of-band edits.

## Trusted totals (`app/resolution/totals.py`)

`day_totals(employee_id, work_date, worked_hours, scheduled_hours, complete, source)` is written only by
trusted server code: provisioning today, imports (A-05) later, and approved corrections.
`load_aggregates` uses the policy week (`rules.week_start`) and quarter (`rules.quarter_start_month`) on local dates.
It returns None (overtime becomes `insufficient_evidence`) when the work date, any other day of the week,
or any finished day of the quarter is missing or incomplete. Days from local today onward count scheduled hours.

## Limits

- Static demo tokens, not an identity provider. PostgreSQL is not yet in Docker or CI (see the Track B request below).
- Only `add_punch` corrections can pass validation today.
- Approval does not require a stored proposal; the server re-validates whatever actions are submitted.
- The corrected punch is stored as a correction row; detail reads still show raw punches plus the resolved status.
- No bulk decisions (A-06) and no escalation persistence yet.

## PostgreSQL setup

```bash
pip install -e "./backend[postgres]"
.venv/bin/python backend/scripts/migrate_postgres.py "postgresql://user@host:5432/resolva"
.venv/bin/python backend/scripts/seed_attendance_demo.py --database-url "postgresql://user@host:5432/resolva"
```

Then set `ATTENDANCE_ENABLED=true` and `ATTENDANCE_DATABASE_URL` in `backend/.env`. Never commit the URL if it contains a password.
Tests: `TEST_DATABASE_URL=postgresql://.../resolva_test pytest backend/tests` runs the PostgreSQL variants.
The database name must end in `_test`, because the fixture drops and recreates its `public` schema.

Requested from Track B (owner of CI and Docker):
- a `postgres:15` service in `.github/workflows/ci.yml`, plus `pip install -e ".[dev,postgres]"` and `TEST_DATABASE_URL`;
- a `postgres` service (profile) in `docker-compose.yml`;
- `psycopg[binary]` pinned in `requirements-dev.lock` if CI should install it.
