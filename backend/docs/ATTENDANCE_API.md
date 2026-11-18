# Read-only attendance demo API

Track A owns these draft endpoints. They use DemoCaseRepository, not the final normalized database schema.
They do not implement corrections, approvals or audit persistence.

## Setup

From the repository root, after installing backend dependencies:

```bash
.venv/bin/python backend/scripts/seed_attendance_demo.py
```

This creates synthetic case X-DEMO-1 for employee E-DEMO-1 and manager M-DEMO-1 under ignored backend/local/.
A random 256-bit bearer token is stored in manager-token.json; only its digest is stored in manager-credentials.json.
Files are created with owner-only permissions where supported. Do not commit or share these credentials.
The credential expires after 24 hours. Provision a fresh directory and configure its paths to rotate it.
Existing credentials are never overwritten by the script. Never point demo provisioning at a shared database.

Set these values in backend/.env (the two paths are optional if using backend/local):

```dotenv
ATTENDANCE_ENABLED=true
# ATTENDANCE_DATABASE_PATH=/absolute/path/attendance.sqlite
# ATTENDANCE_CREDENTIALS_PATH=/absolute/path/manager-credentials.json
```

Start with `.venv/bin/python -m uvicorn app.main:app --reload --port 8000`.
Read the local access_token into your HTTP client's Bearer authorization field; do not paste it into Git.
Swagger at /docs exposes a bearer Authorize control. Disabled attendance returns 503; missing/invalid/expired tokens return 401.
Configuration is loaded on startup; restart after replacing credentials. This is demo authentication, not production SSO or an identity provider.

## HTTP contract

- GET /exceptions: authorized summaries, total count, offset and limit.
  Each summary carries `employee_name` (display only, null when the store keeps no personal data)
  and `status` (open / escalated / resolved).
- GET /exceptions/{exception_id}: authorized CaseContext with evidence_version.
- Missing and unauthorized detail IDs both return 404 without revealing whether a case exists.
- List responses omit employee notes and punch details; detail is restricted to the assigned manager.
- No mutation endpoints exist. Role or manager headers do not override the token's server-provisioned identity.

List parameters:

| Parameter | Values |
| --- | --- |
| exception_type | One of the six ExceptionCode values |
| severity | problem or warning |
| status | open or escalated |
| employee_id, exception_id | Exact string IDs |
| date_range | TODAY, YESTERDAY, THIS_WEEK, LAST_WEEK, THIS_PAY_PERIOD |
| date_from, date_to | Inclusive YYYY-MM-DD bounds; cannot combine with date_range |
| offset, limit | Nonnegative offset; limit 1–100, default 50 |

These names align with Track B's ExceptionQuery. Frontend should send its non-null fields.
Date presets use the provisioned manager's timezone, not the execution host's timezone.
The language module's demo Monday-based weeks and half-month pay periods are reused until calendar contracts are agreed.
Demo snapshots have status open; filtering escalated returns no rows because escalation/decision state is not persisted yet.
Lists order problems first, then work_date and exception_id. Count is manager-scoped and calculated before pagination.
The adapter reads assigned snapshots before filtering; this is appropriate for synthetic demo volumes, not production-scale querying.

## Integration boundaries

- main.py accepts optional AttendanceSettings for tests and reads separate ATTENDANCE_* env variables otherwise.
- Credentials and repository are initialized once per app. Attendance is disabled by default and enabled startup requires provisioned files.
- Manager identity is established by a bearer credential; assignment authorization is enforced in SQL before evidence is returned.
- Case loading revalidates evidence and recomputes its canonical version hash.
- Frontend can use these reads now; do not represent approval as available.
- Final schema/migrations, complete aggregate calculation, identity-provider integration and atomic approval/audit remain pending.
