# Import, detection and bulk decisions (A-05, detection job, A-06)

Track A. Imports and detection need the PostgreSQL store (`ATTENDANCE_DATABASE_URL`); they return 501 on the demo SQLite store.

## Import (`app/attendance/importer.py`, `app/attendance/imports_router.py`)

| Method | Path | Does |
| --- | --- | --- |
| POST | `/imports/preview` | Parse and validate; writes nothing |
| POST | `/imports` | Writes valid rows, then runs detection for touched dates |

Body: `{"kind": "punches"|"shifts", "format": "csv"|"json", "content": "...", "mapping": {...}, "allow_partial": false}`.

- Punch fields: `employee_id`, `timestamp` (or `date` + `time`), `type`, optional `source`, `device_id`, `source_event_id`.
  Shift fields: `employee_id`, `shift_id`, `start`, `end`, `planned_break_min`.
  `mapping` maps these names to your column names; an unknown mapping field returns 422.
- Types accept aliases (`clock_in`, `Clock Out`, `break end`, `meal_start`, ...).
- Times: an ISO time with an offset is kept as is. A naive local time uses the **employee's** timezone.
  A time inside a DST gap or overlap is rejected, never guessed.
- Scope: rows for employees not currently assigned to the manager are invalid. The manager comes from the token.
- Duplicates: the same `(source, source_event_id)`, or the same employee + instant + type, earlier in the file.
  Rows already in the database are also reported. Without a `source_event_id`, a deterministic one is derived,
  so re-importing the same file is a no-op (`UNIQUE (source, source_event_id)`).
- Any invalid row blocks the commit (422 with the row errors) unless `allow_partial` is true.
- CSV and JSON with the same content produce identical records (same ids, same UTC instants).
- Limits: 5,000 rows, 2 MB. Imported text is treated as data only.

## Detection (`app/rules/detection.py`, `app/attendance/ingest.py`)

- Work date = the local date of the clock-in that opens a session. A session stays open until its clock-ins are paired,
  so an overnight clock-out stays with its start date. A punch outside any session uses its own local date.
- Runs the **same** `evaluate_rule_outcomes` as the validator. Only `violation` creates an exception.
  `insufficient_evidence` (for example a shift still running at `as_of`) does not.
- The effective timecard = raw punches + approved `add_punch` corrections, so a resolved exception is not raised again.
- Exception ids are deterministic (`EX-<employee>-<date>-<code>`); a repeat run never duplicates.
  Each new exception gets an `EXCEPTION_DETECTED` audit event (actor `system`).
- Day totals are rewritten for each touched date's whole policy week:
  - `evidence_final` once the shift (or, if unscheduled, the local day) has ended;
  - `complete` when it is also paired.

  Assumption: schedules are imported for every working day, so an unscheduled past day with no punches is 0 h.

## Bulk decisions (A-06)

`POST /exceptions/bulk-decisions` with `{"items": [ {exception_id, ...DecisionRequest} ]}` (1-50 items, unique idempotency keys).
Each item is authorized, validated and committed on its own. One failure never affects another.
The response lists `{exception_id, ok, status_code (200/404/409/422), result | error, checks}` in request order.

## Not done

- Attendance event updates (push) and escalation persistence.
- Shift deletion or amendment through import (append-only for now).
- A detection schedule or cron; detection runs after each import, or by calling `run_detection`.
