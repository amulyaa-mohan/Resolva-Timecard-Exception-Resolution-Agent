# Track A response to the ten SHARED-01 decisions

Prepared by C V Jayanth's coding agent on 2026-11-18 for Amulya's review.
These are Track A's proposed decisions. They do not claim mutual approval or freeze the shared contract.
Shared `core/contracts.py` remains unchanged at `0.1.0-draft`.

1. **IDs:** accept opaque strings. Require nonempty IDs at persistence/API boundaries. The server generates correction/proposal/audit IDs; imported source IDs remain separate provenance fields.
2. **Work date:** accept the local date of shift start in the employee's IANA timezone, including overnight shifts. Require a complete shift-scoped punch set, not a midnight slice. For unscheduled attendance, agree an explicit session grouping strategy before enabling correction eligibility.
3. **Evidence version:** use SHA-256 of canonical UTF-8 JSON, sorted object keys and stable punch/note ID ordering; UTC microsecond ISO timestamps; no NaN values. Include employee context, exception/rule identity, work date, punches, history, schedule, notes, detection details and a monotonic correction revision. Exclude the hash itself. `build_verified_case` implements the draft recipe. Final storage must atomically increment the revision for every correction and supply effective attendance plus original provenance. Policy content hash/version and permissions must be checked separately at approval. A hash is not authentication.
4. **Validator:** target resolution plus no new problems OR warnings is required. Proposed conservative MVP: unresolved violations also block until there is an explicit reviewed acknowledgment/premium disposition model. Acknowledgment cannot mean deleting evidence of a breach. Return all six checks; unsupported actions, insufficient history or missing rules must fail closed. Our partial adapter deliberately returns passed=false.
5. **Action targets:** propose fields now, implement through a reviewed shared-contract revision: shift_id for void_shift; shift_id, break_start and break_end for add_break; source_shift_id and replacement_shift_id for schedule swaps; explicit source finding/reference for acknowledge or premium. Validate action-specific required/forbidden fields, ownership and chronology. Until agreed, these actions must be rejected by the validator. The current validator supports only simulated add_punch on missing-punch cases and still blocks approval.
6. **Manual corrections:** accept reusing ProposedAction, with the same server validator and allowed-action checks. A manual entry still requires actor identity, evidence, reason and a current context; it never bypasses safety gates. ProposedAction.note is not proof that a punch or break happened.
7. **Audit:** Track A owns the draft. Required fields: audit_id, UTC timestamp, authenticated actor_id/role, event type, employee/entity IDs, trace_id, before/after evidence versions, correction/proposal IDs, reason, action payload, rule version and validation checks. AI-originated events additionally reference model_id, prompt_hash/version, policy pack/version/content hash and trace storage ID. Manual events may have null AI fields. Keep immutable evidence references, redact unnecessary free text and restrict raw model traces. Correction and approval audit must commit atomically.
8. **Persistence:** accept proposals and llm_traces tables as the final design direction, linked to exceptions and correction/audit records with explicit retention and access rules. Database team owns migrations; Track A coordinates compatibility. The new DemoCaseRepository is an isolated disposable SQLite integration adapter, not a competing final schema or migration system. It is not wired into application startup.
9. **Routes:** accept Track A ownership of exceptions/proposals orchestration and decision routes, calling Track B services. Only /health exists now. Manager identity must come from an authenticated server dependency, never a query parameter or freely trusted role header. CaseService accepts manager_id only as an internal trusted argument. API authentication and endpoint contracts remain pending.
10. **Severity:** accept DEFAULT_SEVERITY exactly as drafted. Case loading rejects inconsistent severity. Severity is assigned by rules, not the LLM or client; warning-level outcomes still participate in validation.

## Additional findings requiring joint agreement

- Frozen models contain mutable lists/dicts. They are shallowly immutable; deep-copy/revalidate at boundaries and avoid sharing mutable instances across requests. Consider tuples in a future contract revision.
- Add an explicit as_of/evaluation time to CaseContext so live open shifts are not treated as overdue. Do not reinterpret missing_punch_window_min (an inference tolerance) as an overdue closing grace.
- Weekly/quarterly rules require complete aggregates/history and remaining scheduled work; seven days of raw history alone cannot establish every limit. Missing inputs must block eligibility.
- Evidence completeness must establish actual attendance, not infer a break just because planned_break_min is nonzero.
- Version changes should bump CONTRACT_VERSION only after both tracks agree. The new Track A code adapts the existing draft without modifying Track B modules.

## Current integration behavior

CaseService loads a manager-scoped snapshot, validates identity/date consistency and computes evidence_version.
Track B's real offline pipeline calls Track A's CorrectionValidator-compatible adapter.
The adapter reuses the existing missing-punch detector and returns failed checks for unfinished rules.
The resulting proposal is BLOCKED; it must not be presented as approval-ready.

## A-RULES-03 — Proposals awaiting Track B answers (2026-11-18, not agreed)

Current code: `app/rules/validator.py` exposes `validate_correction` (no aggregates, always fails closed on overtime) and `make_validator(load_aggregates)`, which keeps the three-argument CorrectionValidator interface. No shared contract or Track B module changed. Questions for Amulya:

1. Aggregate delivery. Proposal: Track A binds a trusted aggregate loader into the validator (`make_validator`) and no CaseContext field is added. Alternative: a 0.1.x `CaseContext.aggregates` field filled only by the backend loader, never by models or clients. Which do you prefer for SHARED-02?
2. Insufficient evidence vs violation. Today both are `RuleCheck.passed=False` and the pipeline returns BLOCKED; the difference appears only in the reason text. Proposal: add `RuleCheck.outcome: "pass" | "violation" | "insufficient_evidence"` (keeping `passed` for compatibility), and have the pipeline ESCALATE when any check is insufficient_evidence and none is a violation. OK?
3. Time anchoring. Your time-evidence gate accepts an added punch within 5 minutes of the schedule, a note-stated time or history. The validator accepts only the exact schedule boundary. Proposal: the validator stays exact until a verified time-evidence field exists (for example `ProposedAction.evidence_ref` naming a note_id or history punch_id that the validator re-checks). Does this match the prompt's expected outputs and your eval labels?
4. Evals. Swapping `validate_correction` into `evals/run.py` will block eval cases that lack break punches or aggregates. Should the eval fixtures gain complete evidence plus a fixture aggregate source, or should evals report both validators side by side?
5. Calendar and evaluation time (unchanged from earlier): the policy week start, the quarter definition, and a `CaseContext.as_of` field for open shifts.

### Answers from Amulya (relayed by Jayanth, 2026-11-18): agreed

1. Totals reach the validator through `make_validator`; CaseContext is unchanged. The loader re-reads totals on every validation, including at approval. The totals used, their periods and their as-of time are recorded. Done in Track A: they are written into the OVERTIME_RISK reason; the audit record follows in A-03.
2. Agreed: `RuleCheck.outcome` = `pass | violation | insufficient_evidence`, with `passed == (outcome == "pass")`. Pipeline: any violation gives BLOCKED; otherwise any insufficient_evidence gives ESCALATED; ELIGIBLE only when every check passes. Track A already classifies outcomes (`evaluate_rule_outcomes`) and will populate the field when 0.2.0 lands.
3. The validator stays exact-time for the MVP. Contract 0.2.0 adds `ProposedAction.evidence_ref` (a note, punch or schedule id) and a single policy field `evidence_tolerance_min` (5 in the demo packs). The validator will then accept a time within that tolerance of the referenced evidence.
4. Evals (Track B owns evals/): complete-evidence fixtures using the loader shape in RULE_ENGINE.md, deliberately incomplete cases expected to be ESCALATED, and reports showing the stand-in and real validators side by side until the numbers are stable. CI is then gated on the real validator.
5. Policy pack fields `week_start: monday` and `quarter_start_month: 1`. Quarters are calendar quarters in the employee's local timezone; the Indian Factories Act definition still needs confirming before the demo. `CaseContext.as_of` is an aware UTC time set by the server at load. It is excluded from evidence_version and recorded in the audit.

Contract process: all 0.2.0 changes (items 2, 3 and 5) go in one commit. Amulya proposed that she does contracts.py and the pipeline, and Jayanth reviews; Jayanth has not confirmed this yet. She pulls `backend` first, and the two tracks stay on separate files.
After 0.2.0, Track A: populate outcome; accept evidence_ref within evidence_tolerance_min; check the week_start weekday and quarter_start_month in the aggregate check; use as_of for open shifts.

### Contract 0.2.0-draft adopted by Track A (2026-11-18)

Track B's 1c4e895 was pulled without conflicts. Track A now:
- sets `outcome` on every RuleCheck;
- accepts `new_ts` within `evidence_tolerance_min` of the `evidence_ref`, and stays strict without one;
- sets `as_of` in CaseService and the resolution store, excluded from `evidence_version`;
- uses `week_start` and `quarter_start_month` from the policy.

Totals still go through `make_validator`. Quarters are settled as calendar quarters (`quarter_start_month: 1`).
Open question for Track B: an evidence-backed clock-out later than `late_tolerance_min` introduces a
SCHEDULE_DEVIATION violation (BLOCKED). Should a warning-severity deviation instead escalate for manager review?

### New questions for Track B (2026-11-18, A-05/A-06/item 7)

1. `adjust_punch`: Track A accepts it only with a `note` evidence_ref within `evidence_tolerance_min`;
   schedule and history refs are refused for moving a recorded punch. Your time-evidence gate reads
   `action.punch_type`, which adjust actions may leave empty. Can the gate use the target punch's type
   (`case.punches` by `punch_id`) and attach only `note` refs for adjustments?
2. Semantics needed before Track A validates them:
   - `acknowledge`: close the exception with no timecard change; is a manager reason enough?
   - `add_break`: two timestamps (start and end) do not fit one `new_ts`; two actions, or a `new_end_ts` field?
   - `void_shift`: what does it target (shift_id, or the punch_ids of the duplicate session)?
   - `flag_premium`: a pay flag, not a timecard change; does it resolve the exception?
   - `suggest_schedule_swap`: advisory only, never approvable?
3. Detected exceptions now come from imports (ids `EX-<employee>-<date>-<code>`, `detection_details.reason`).
   Is that enough for your retrieval queries, or do you need structured detail keys per code?

### Track B answers (2026-11-18, Amulya)

1. **`adjust_punch`: yes, done.** The time-evidence gate (`anchor_times` in `app/ai/evidence.py`) now
   handles `adjust_punch` for every exception code. The target must be one of `case.punches` (by
   `punch_id`), and its type is read from that punch. Only `note` refs are attached; schedule and
   history refs are refused (including model-supplied ones); no time after `as_of`. The validator
   receives the adjustment with the note ref. Tests: `tests/unit/test_contract_v020.py`.

   **New point for both of us (pay integrity):** a tolerance applied in both directions can grant time
   nobody claimed. Example, verified end to end with your validator: the note says "at the gate at
   09:05" and an adjustment to 09:00 (the scheduled start) is ELIGIBLE, because 09:00 is within 5 min
   of 09:05. Proposal: round a stated time only in the direction that does not add paid time, so a
   clock-in may be at or after the stated time, and a clock-out at or before it, by up to
   `evidence_tolerance_min`. Schedule-anchored `add_punch` keeps the two-sided tolerance, because
   the schedule is the agreed time. If you agree, we each enforce it (gate and validator) and add
   one shared test.

2. **Semantics.** These are proposals. Fields marked *new* need contract `0.3.0-draft`, and I will
   draft that once you agree.
   - **`acknowledge`:** closes a *warning* exception (OVERTIME_RISK, SCHEDULE_DEVIATION) with no
     timecard change. It needs a non-empty manager reason, which is audited. It is never valid for a
     *problem* severity, and it never deletes or hides the finding; the breach stays in evidence. The
     AI may propose it with a citation, but it is never bulk-approvable.
   - **`add_break`:** one action with `new_ts` (break start) and *new* `new_end_ts` (break end). It is
     atomic: two separate actions could be half-validated or half-applied. Both times need `note`
     evidence, because `planned_break_min` never proves a break. Without stated times the right
     action is `flag_premium` or escalation, never an invented break.
   - **`void_shift`:** targets the attendance session, not the schedule. *New* field
     `target_punch_ids: list[str]` names the duplicate session's punches. All of them must belong to
     this case. Every remaining punch must still pair. It can never void the only session for the
     work date. Raw punches stay immutable: voiding is a correction record that excludes them.
   - **`flag_premium`:** a pay flag (meal-break premium owed), no timecard change. It resolves
     MEAL_BREAK_BREACH as "breach confirmed, premium flagged". The validator must confirm the breach
     is real (a premium for a non-breach is unearned pay), and the breach stays recorded in audit.
   - **`suggest_schedule_swap`:** advisory only. It is never approvable and never resolves an
     exception. I will make the pipeline return such a proposal as ESCALATED with the suggestion
     attached, so it can never show as ELIGIBLE.

3. **`detection_details`:** `reason` is enough for retrieval today. Queries use the exception code's
   own terms plus the detail *key names*, never values. Structured keys per code would help the
   model's `<facts>` and the manager's explanation, so please add them when convenient:
   MISSING_PUNCH `unmatched_punch_id`, `missing_type`; OVERLAPPING_SHIFT `overlapping_punch_ids`;
   MEAL_BREAK_BREACH `worked_min_before_break`, `break_min`; OVERTIME_RISK `day_hours`,
   `projected_week_hours`, `limit_hours`; SPREAD_OVER_BREACH `spread_hours`; SCHEDULE_DEVIATION
   `boundary` (start or end), `minutes_off`.

4. **Earlier question, evidence-backed late clock-out:** escalate. A warning-severity
   SCHEDULE_DEVIATION created by a correct, evidenced fix should return `insufficient_evidence` with
   a reason ("fix is evidenced but leaves a warning: manager review"), not `violation`. A manager can
   then approve or acknowledge it. Problem-severity rules keep blocking.

5. **CI:** a `postgres:15` service now runs in CI with `TEST_DATABASE_URL`, and `.[dev,postgres]` is
   installed (`psycopg[binary]` 3.3.9 pinned). A guard step fails the build if any PostgreSQL test is
   skipped. Docker has a `postgres` profile (127.0.0.1 only), and the API image installs the
   `postgres` extra. Verified locally on PostgreSQL 15.20: all 466 tests pass, including your 31.

### Track A reply (2026-11-18, Jayanth): agreed and implemented

1. **Pay integrity: agreed, and your example now fails.** A time the employee *stated* (a `note`
   ref) may only be rounded in the direction that adds no paid time: a clock-in at or after it, a
   clock-out at or before it, a break start at or before it, a break end at or after it, each by up
   to `evidence_tolerance_min`. Your 09:05 -> 09:00 adjustment is refused with
   "not within 5 min of the stated time in the direction that adds no unclaimed paid time".
   Schedule-anchored `add_punch` keeps the two-sided tolerance, as you proposed.
   Tests: `test_stated_time_rounding_never_adds_paid_time`, `test_schedule_anchor_keeps_both_directions`.
   **One open question:** `history_punch` refs are still two-sided. A habit is not a claim, so the
   same one-sided rule arguably belongs there too, but your gate attaches those refs, and a
   one-sided validator would block proposals your gate accepted. Shall we make both sides one-sided
   for history in 0.3.0?
2. **Semantics: your five proposals all work for Track A.** Please draft 0.3.0 with
   `new_end_ts` (add_break) and `target_punch_ids` (void_shift). Two notes:
   `flag_premium` needs the validator to confirm the breach is real, which it can already do
   (the simulated timecard still shows MEAL_BREAK_BREACH), and `acknowledge` must stay out of bulk
   decisions, so Track A will refuse it there rather than relying on the prompt.
3. **`detection_details`: agreed, not done yet.** Detection currently writes `{"reason": ...}`.
   The structured keys you listed are the next Track A change; nothing in the contract blocks it.
4. **Evidenced fix leaving a warning: agreed and implemented.** When a correction carries evidence
   and the only remaining failure is SCHEDULE_DEVIATION, the validator now returns
   `insufficient_evidence` with "Fix is evidenced but leaves a warning: manager review", so the
   pipeline escalates instead of blocking. Problem-severity remainders still block.
5. **CI: thank you.** Track A's PostgreSQL tests now run on every build.

### Track B reply (2026-11-18, Amulya): history rounding and step 2

- **History refs: yes, one-sided.** Track B's gate now rounds `history_punch` times one way only
  (a habit is not a record), as it does for notes; schedule refs stay two-sided. Your validator can
  make history one-sided too; until then the gate is the stricter of the two, so nothing it accepts
  can be refused by your rule for adding paid time.
- **Step 2 is live on Track B's side:** the pipeline now drafts `adjust_punch` fixes for
  SCHEDULE_DEVIATION, SPREAD_OVER_BREACH and OVERLAPPING_SHIFT, escalating without the model when no
  usable stated time exists. Prompt `propose_v3` adds the adjustment rules. Eval category
  `adjustment` (12 cases, `evals/cases/adjustment.json`) runs against your real validator.
- **0.3.0-draft** (`new_end_ts`, `target_punch_ids`, swap never approvable) is next on Track B's list.

### Track A reply to the code audit (2026-11-18, Jayanth): reviewed, confirmed, and three of your asks done

I pulled `b2c7a86`, read the diff, and ran the full suite with `TEST_DATABASE_URL`: **550 passed** before my
changes and **580** after. Thank you for the audit. No need to apologise for touching these files.

**Reviewed and agreed**
- **A1 (meal break):** correct. The walk now resets the count only after a rest of `rest_minutes`, so 13:00 out and
  13:01 in no longer passes. The detection details I added use the same walk.
- **A2 (propose):** correct, and a real improvement. Reading the totals once before the model call is fine
  because a proposal is only a draft: approval re-reads totals and re-validates, and the short write re-checks the
  revision and evidence hash. I checked that a stale result returns 409 and that nothing is persisted in that case.
- **A3 (trace keys):** agreed; retention and the integrity check both join on the key, and the audit payload keeps
  the raw id for display.
- **A4 (unsupported types escalate):** agreed.
- **A6 (`effective_to` exclusive):** agreed, now consistent with the registry.

**A5 confirmed, and it was my bug.** KA-9 and US-6 define a deviation as a clock-in more than 7 minutes *after* the
scheduled start or a clock-out more than 7 minutes *before* the scheduled end. My check was two-sided, so it also
flagged arriving early or leaving late, which the policy text does not call a deviation. Early arrival and late
departure are extra paid time, and OVERTIME_RISK is the right place for them. No change requested.
One open point (also in RULE_ENGINE.md): the design README lists "an unscheduled shift" as a deviation. With no
schedule we return `insufficient_evidence`, because we cannot tell a missing schedule import from a genuinely
unscheduled shift. Treating it as a violation needs an agreed signal that schedules are complete for the day. Your view?

**Done, as you asked**
1. **Structured `detection_details`.** Every exception now stores the keys you listed, next to `reason`:
   `unmatched_punch_id` / `missing_type`, `overlapping_punch_ids`, `worked_min_before_break` / `break_min`,
   `day_hours` / `projected_week_hours` / `limit_hours`, `spread_hours`, `boundary` / `minutes_off`.
   I added `limit_kind` (`daily`, `weekly`, `quarterly`) to OVERTIME_RISK, because three limits make `limit_hours`
   ambiguous. They are scalars only, and an undecided finding gets none. Source: `app/rules/explain.py`.
2. **Employee notes.** `POST /imports` now takes `kind: "notes"`. A note attaches to an open or escalated exception
   when it was written on the work date or the day after; attaching changes `evidence_version` (so earlier drafts go
   stale) and is audited as `EVIDENCE_ATTACHED`. A note imported before its exception exists is attached when
   detection raises it. The demo seed imports four notes, each stating a time, one per late-arrival, spread-over,
   overlap and forgotten-punch case. Details: `backend/docs/IMPORT_DETECTION.md`.
   While building this I made the window too wide first (7 days), saw Friday's note attach to Tuesday's exception in
   the seed output, and tightened it to two days. A note has no date of its own, so please keep in mind that it may
   still be about the other day inside the window; the model should treat a note's time as a claim, as it does now.
3. Tests: `test_explain.py` (15), the notes cases in `test_import_detection.py` and `test_import_flow_pg.py`.

**Still to do together:** review contract 0.3.0-draft once you post it. Nothing in the notes or details work
depends on it.

### Track B reply (2026-11-18, Amulya): verified 090bbdd live; two fixes; your question

Pulled 090bbdd: 585 tests pass on PostgreSQL (none skipped), CI green. With your notes in the demo week,
I ran every exception through the Docker stack with live Qwen2.5-7B. The demo story now works end to end:
approve Tuesday's missing punch, then Friday's late arrival becomes eligible (it escalated before,
because Tuesday's hours were unknown), and approving it moves the clock-in to the stated 09:05.

**Two bugs found by the live run, both fixed:**
1. *Track B:* the model saw PostgreSQL's UTC timestamps (`09:25+00:00`), copied that offset as told,
   and wrote the stated 09:05 as `09:05+00:00` (14:35 IST), so every adjustment was blocked. The case
   JSON now shows the employee's local time (`_localised` in `app/ai/pipeline.py`).
2. *Track A (`store.decide`):* approving an `adjust_punch` returned 500. Approval built the corrected
   timecard by adding every action as a new punch, which crashed on the empty `punch_type`, and would
   have double-counted the hours written to `day_totals`. Approval and the timecard read now share
   `apply_actions` (add adds, adjust moves). Test: `test_approving_an_adjustment_applies_it_once` on
   SQLite and PostgreSQL; it fails on the old code.

Also on Track B: the pre-model gate now ignores a stated time that *equals* a recorded punch. Your
overlap note "my real shift was 9:00 to 6:00 pm" restates the existing punches, so the double tap now
escalates cleanly (voiding the duplicate needs 0.3.0's `target_punch_ids`).

**Your question: should an unscheduled shift be a deviation?** Keep `insufficient_evidence` by default,
as you have it. KA-9 and US-6 define deviations against a schedule, and with no schedule we cannot tell a
missing import from a real unscheduled shift. Proposal for 0.3.0: a trusted "roster final" signal per
employee and date (written by the shift import, like `evidence_final` for punches). With the roster final,
no shift and recorded work, it becomes a SCHEDULE_DEVIATION violation ("unscheduled shift", warning).
The fix is `acknowledge` with a manager reason, never an invented schedule, so the AI only explains and
escalates it.

**Two points for you:**
- *Spread-over demo:* the evidenced fix (06:30) cures the spread, but the day still has 10 h worked
  against a 9 h daily limit, so OVERTIME_RISK blocks it. Should your "evidenced fix that only leaves a
  warning → manager review" rule cover warning-severity OVERTIME_RISK as well as SCHEDULE_DEVIATION?
  The overtime was really worked and must be paid, so escalating seems right to me.
- *Timecard display:* `GET /exceptions/{id}/timecard` returns raw punches in UTC next to corrections
  in local time (`03:55` beside `09:05`). Same instants, but the frontend should get one zone; the
  employee's local zone would match the rest of the API.

### Decisions settled (2026-11-18, Amulya, implemented by Track B at the owner's request)

1. **Unscheduled shift:** stays `insufficient_evidence` (no change). It becomes a SCHEDULE_DEVIATION
   warning only once a trusted "roster final" signal exists; that is part of contract 0.3.0.
2. **Warnings left after an evidenced fix go to the manager.** `_warning_needs_review` in
   `app/rules/validator.py` now covers OVERTIME_RISK as well as SCHEDULE_DEVIATION, and any number of
   them, as long as every remaining failure is a warning-severity violation and every action carries
   evidence. Any problem-severity failure still blocks. Escalation never approves: approval still
   re-validates and refuses it. Live demo: the spread-over fix to the stated 06:30 (10 h worked, late
   start) now escalates for review instead of blocking. Tests: `test_evidenced_fix_leaving_several_warnings_is_reviewable`,
   `test_a_problem_remainder_still_blocks_even_with_warnings`, and your
   `test_evidenced_fix_that_creates_overtime_goes_to_the_manager` (renamed; it asserted the old answer).
   Eval case e03 now expects ESCALATED, matching its own description ("needs overtime review").
3. **Timecard time zone:** `GET /exceptions/{id}/timecard` returns every time (raw punches, effective
   punches, applied actions) in the employee's zone, and states it in a new `timezone` field.
   Test: `test_timecard_reports_every_time_in_the_employee_zone`.
