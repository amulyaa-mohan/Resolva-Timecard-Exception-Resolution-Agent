# Track A self-audit, 2026-11-18

Scope: the Track A code written **after** Track B's audit (`docs/shared/AUDIT_2026-11-18.md`): import, detection,
notes, structured details, the effective-timecard path, and the frontend wiring. Method: read each path as an
adversary, write a failing test for each suspicion before fixing it, and measure rather than guess.
Every finding below was reproduced first. Items that turned out fine are listed too.

## Fixed

| # | Severity | Finding | Reproduced by | Fix |
| --- | --- | --- | --- | --- |
| 1 | High | **Approving any `adjust_punch` returned HTTP 500.** The approval path built a punch for every action using `punch_type`, which is empty for an adjustment. Only the validator had been tested for this action, never an approval. Three places each re-implemented "apply corrections to punches", each handling a different subset. | `test_approving_an_adjust_punch_moves_the_punch_instead_of_adding_one` (both stores) | One shared `app/resolution/apply.py`, used by the timecard view, the approval path and detection |
| 2 | High | **An exception never cleared.** A punch imported after detection left the exception open forever, and the validator then said "the problem is no longer present", so the manager could not resolve it. | `test_an_exception_is_cleared_when_later_data_fixes_it` | Detection dismisses an exception whose rule now passes (audited `EXCEPTION_CLEARED`), never on mere insufficient evidence |
| 3 | High | **A cleared exception could never return** (its deterministic id was already taken), and new punches on a live exception were never linked as evidence. | `test_a_cleared_exception_comes_back_if_the_problem_returns` | Recurrence reopens it (`EXCEPTION_REOPENED`); new day punches are linked and audited |
| 4 | High | **A retry after a failed detection detected nothing.** The import commits first; on retry every row is "already imported", contributed no dates, so those dates were never re-checked. Same class as the notes bug found earlier. | `test_a_retry_after_a_failed_detection_still_detects` | Already-imported rows still tell detection which dates to re-check (idempotent) |
| 5 | Medium | **Hostile files produced HTTP 500**: a CSV cell over 128 KB, JSON nested 100,000 deep, a 5,000-digit JSON integer, and a year-0001 timestamp (`OverflowError`). | the probe in `test_hostile_files_are_rejected_cleanly` and `..._implausible_years_...` | All become 422. Cells capped at 4,000 chars, years 2000-2100, request body capped at 2 MB |
| 6 | Medium | **Values the parser accepted but PostgreSQL would reject at insert:** a NUL byte (also hidden as the JSON escape `\u0000`, which only exists after decoding) and a 30-digit `planned_break_min` (overflows a 32-bit column). | `test_hostile_import_bodies_are_422_not_500`, `test_planned_break_is_bounded` | Rejected at the boundary; break length 0-1440 |
| 7 | Medium | **One long write transaction for a whole import.** Every writer shares one lock, so a 5,000-row import of one punch per employee would stall every approval for about 24 s (measured: 5 ms per employee; 120 employees take 0.58 s). | `test_detection_releases_the_write_lock_between_employees` | One committed transaction per employee; a part-way failure keeps earlier work and a retry finishes |
| 8 | Medium | **CSV formula injection in the audit export** (frontend): a rejection reason beginning with `=` becomes a live formula when an auditor opens the file in a spreadsheet. | read of `SecondaryViews.tsx` | See the frontend commit |

## Checked and fine

- **Fuzzing:** 6,000 random days (orphan breaks, simultaneous times, mixed timezones, DST months, overnight) through
  `detect`, `explain`, `group_by_work_date`, `net_worked_hours` and `apply_corrections`: no exception, and every
  `detection_details` key was in the agreed set and scalar.
- **Concurrent approvals:** the four-thread race still leaves exactly one winner after the per-employee change.
- **Cross-employee data:** the integrity check finds no cross-employee evidence after notes, clearing and reopening.
- **Frontend sinks:** no `dangerouslySetInnerHTML`, `eval`, `innerHTML` or open redirect; React escapes all text.
  The token is kept in `sessionStorage`, readable by script on the page: acceptable only because no injection sink
  exists, and it is cleared on sign-out and on any 401.

## Not fixed, on purpose

- **An unscheduled shift is not flagged** as a deviation (open question with Track B).
- **A note could be about the other day** inside its two-day attach window. The model must keep treating a note's
  time as a claim, and a manager sees the note with the case.
- **`attach_notes` is O(exceptions x notes)** per employee. Fine at demo scale; revisit with real volumes.
- **Static demo tokens**, not an identity provider.
