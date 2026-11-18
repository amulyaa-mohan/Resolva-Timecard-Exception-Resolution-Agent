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
- A clock-in on a later local date starts a new session, and nothing stays open beyond the following day.
  An unpaired clock-in therefore stays on its own date instead of swallowing the days after it
  (found by the demo seed: one missing clock-out used to absorb the rest of the week).
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

## Lifecycle of an exception

Detection re-runs for every date an import touches, including rows already on file, so a retry after a failure heals.

- **Raised** when a rule is violated: `EXCEPTION_DETECTED`.
- **Cleared** (`status = dismissed`, audited `EXCEPTION_CLEARED`) when its rule now *passes* after new evidence.
  A rule that is merely undecided is left alone: not knowing is not the same as fixed. Dismissed exceptions are hidden from
  the default list and returned by `?status=dismissed`.
- **Reopened** (`EXCEPTION_REOPENED`) if the problem returns, keeping its id.
- New punches joining a live exception are linked as evidence and audited, which changes its `evidence_version`.
- Detection commits **one transaction per employee**, so the global write lock is held for milliseconds, not for the
  whole import.

## Input limits

Every violation is a 422 with a problem document, never a 500: body and file 2 MB, 5,000 rows, cells 4,000 characters,
notes 1,000, timestamps years 2000-2100, `planned_break_min` 0-1440, no NUL bytes (including the JSON escape).

## Employee notes

`POST /imports` with `kind: "notes"` (fields `employee_id`, `submitted_at`, `text`, optional `note_id`).

- Text is untrusted data: stored verbatim, up to 1000 characters, never interpreted as an instruction.
  A longer note is rejected, not truncated.
- A naive `submitted_at` is read in the employee's timezone (DST gaps and overlaps are refused, as for punches).
- The note id is derived from the employee and the content, so a re-import is a no-op and one employee's
  id can never overwrite another's note.
- A note attaches to an employee's **open or escalated** exception when it was submitted on the exception's
  work date or the day after (local time). A note has no date of its own, so this window is the whole rule;
  it is deliberately tight so a note about Friday is never evidence for Tuesday. A resolved exception's
  evidence is never changed.
- Attaching changes the case's `evidence_version`, so a draft made before the note arrived is stale, as it should
  be. Each change is audited as `EVIDENCE_ATTACHED`. Import and attach are one transaction.
- A note imported before its exception exists is attached when detection raises it.

## Structured `detection_details`

Every exception stores scalar facts next to the human-readable `reason`, for the model's facts block and the
manager's explanation. They describe a violation the engine already found and never decide one; an
undecided (insufficient-evidence) finding gets none. Source: `app/rules/explain.py`.

| Code | Keys |
| --- | --- |
| MISSING_PUNCH | `unmatched_punch_id`, `missing_type` (`in` or `out`) |
| OVERLAPPING_SHIFT | `overlapping_punch_ids` (comma-separated) |
| MEAL_BREAK_BREACH | `worked_min_before_break` (longest stretch without a qualifying rest), `break_min` (longest break recorded) |
| OVERTIME_RISK | `day_hours`, `projected_week_hours`, `limit_hours`, `limit_kind` (`daily`, `weekly` or `quarterly`) |
| SPREAD_OVER_BREACH | `spread_hours` |
| SCHEDULE_DEVIATION | `boundary` (`start` or `end`), `minutes_off` |

`limit_kind` is an addition to the keys Track B listed: with three possible limits, `limit_hours` alone is ambiguous.

## Demo data

```bash
.venv/bin/python backend/scripts/seed_demo_week.py "postgresql://user@host:5432/resolva"
```

It writes three synthetic employees and last week's shifts and punches, imports them through the
real preview and commit path, and lets detection raise all six exception types (plus one clean day).
It imports four employee notes through the real notes path, each stating a time (a forgotten punch-out, a kiosk outage, a late gate opening, a double tap), and each lands on exactly one exception.
It also writes synthetic day totals from the quarter start, because one week of punches cannot
establish a weekly or quarterly limit; without them OVERTIME_RISK is correctly undecidable.
A manager credential is written to the ignored `backend/local/` unless one is already there.

Note: an unpairable day (a missing punch, an overlap) makes that employee's week unknown, so other
cases in the same week escalate on overtime until it is resolved. The seed puts the overlap case on
its own employee for that reason. Resolving the missing punch makes its week decidable again.

## Not done

- Attendance event updates (pushing approved corrections to an external HCM system).
- Structured `detection_details` keys per exception code (agreed with Track B; next Track A change).
- Shift deletion or amendment through import (append-only for now).
- A detection schedule or cron; detection runs after each import, or by calling `run_detection`.
