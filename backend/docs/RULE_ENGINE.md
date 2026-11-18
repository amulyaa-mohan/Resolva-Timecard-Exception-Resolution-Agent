# Deterministic attendance checks

Track A implementation: `backend/app/rules/engine.py`.
Version: `attendance-rules@0.4-draft` (contract 0.2.0). Uses simplified demo policy configuration, not legal certification.

## Entry points

- `evaluate_rules(case, policy, aggregates=None)` returns six RuleCheck results for a closed work-date context.
- `validate_correction(case, actions, policy)` simulates a supported correction on a copy and calls evaluate_rules again. With no aggregate source, overtime and approval stay failed closed.
- `make_validator(load_aggregates)` returns a validator with the same three-argument interface, bound to a trusted backend aggregate source. A loader that returns None, raises, or returns a non-AggregateEvidence value fails closed.
- The earlier `missing_punch.py` remains the isolated shift-level/grace-period helper used by the initial tests. The integrated validator uses engine.py for every check.

## Checks

| Rule | Calculation |
| --- | --- |
| Missing punch | FIFO work pairing; no unmatched in/out events; no empty attendance evidence |
| Overlap | Paired work intervals must not overlap; incomplete pairing blocks |
| Meal break | Observed paired breaks inside exactly one shift, meeting configured duration before the work threshold |
| Overtime | Net observed hours versus daily limit; other-day worked plus remaining scheduled hours versus weekly limit; quarterly aggregate versus configured cap |
| Spread | Elapsed UTC time from first clock-in to last clock-out versus configured maximum |
| Schedule | First/last work boundary versus scheduled boundaries and minute tolerance |

A failed RuleCheck can mean a detected violation or insufficient/ambiguous evidence. The reason states which.
Do not persist every failed check as a confirmed exception: a richer detection outcome contract remains to be agreed.
Exact positive policy thresholds are inclusive: exceeding the limit fails. This demo interpretation needs policy-owner review before real use.
Actual recorded breaks are used; planned_break_min does not prove a break occurred.
Ambiguous equal-time events fail closed. No attendance events means unknown/absence, not a fabricated missing punch.
All elapsed-duration arithmetic uses UTC, including daylight-saving transitions.
Scope: work_date is the local shift-start date. Any clock-in on another local date blocks all checks, so it cannot be double-counted. Overnight clock-outs stay in scope. One timezone per employee context: a location or timezone change within a work date is not modelled and needs a contract.

## Aggregate input proposal

AggregateEvidence is an internal rules input, not a model-generated or HTTP field:
- work_date_complete: trusted certification that case punches include the full work date.
- week_other_worked_hours: worked hours in the policy week excluding the case work date.
- week_remaining_scheduled_hours: remaining scheduled hours excluding the case shift, with already worked time removed.
- quarter_other_overtime_hours: overtime already accumulated, excluding this work date.

Incomplete, negative or nonfinite totals cannot establish eligibility. Employee week boundaries, quarter boundaries,
policy-specific daily splitting and source provenance require database/policy contract agreement.
No values are read from detection_details as trusted aggregate evidence.
The shared CaseContext currently has no aggregate contract, so validate_correction cannot pass the overtime check. make_validator can pass it once a trusted loader exists. The loader must exclude the case work date from week and quarter totals; the validator cannot verify this exclusion.
A complete trusted AggregateEvidence allows standalone engine checks to pass; it is not exposed as an approval bypass.

## Supported simulation and limitations

Only one add_punch for a missing work clock-in/out is simulated today.
An exact scheduled boundary is accepted as the current candidate anchor; other times need a verified-time evidence contract.
The policy inference window is checked separately; simply falling inside it is not evidence.
Already resolved cases, break-punch additions, existing punch targets and simulation-ID conflicts are rejected.
Other correction action types remain blocked pending target fields and evidence semantics.
The validator never writes records and does not authorize a manager.
Live/open-shift evaluation still needs an as_of and closing-grace contract. Engine evaluation is closed-context only.
Multiple-schedule association and full policy-specific weekly/quarterly calculation are not inferred from the draft context.
These limits prevent approval eligibility until the shared evidence and persistence contracts are completed.

## Outcomes (agreed for contract 0.2.0)

`evaluate_rule_outcomes` returns `(RuleCheck, Outcome)` pairs; `evaluate_rules` returns the checks only. `passed == (outcome == PASS)` always.
- VIOLATION: the evidence decides the rule and it fails, for example unpaired work punches, overlap, a missing, short or late break, hours over a limit, excess spread, or a time outside schedule tolerance.
- INSUFFICIENT_EVIDENCE: the rule cannot be decided. Examples: no applicable policy, no punches, simultaneous punches, a clock-in on another local date, rules that depend on unpaired work, no schedule, or missing or mis-period totals.
Validator-level rejections (unsupported action, inexact time) stay plain failed checks until RuleCheck.outcome exists.

## Aggregate loader shape (for Track B eval fixtures)

```python
from app.rules.engine import AggregateEvidence
from app.rules.validator import make_validator


def load(case):  # trusted backend source; called on EVERY validation
    return AggregateEvidence(
        work_date_complete=True,  # case.punches hold the whole work date
        week_other_worked_hours=32.0,  # policy week, excluding case.work_date
        week_remaining_scheduled_hours=8.0,  # later scheduled shifts this week
        quarter_other_overtime_hours=4.0,  # calendar quarter, excluding case.work_date
        week_start=date(2026, 11, 9),  # local date; must contain case.work_date
        quarter_start=date(2026, 10, 1),  # first day of Jan/Apr/Jul/Oct
        as_of=datetime(..., tzinfo=UTC),  # when the totals were read
    )


validator = make_validator(load)  # same (case, actions, policy) interface
```

Return None when totals are unavailable: overtime is then INSUFFICIENT_EVIDENCE. A loader that raises, or returns another type, blocks every check.
The OVERTIME_RISK reason records the day hours, each total, its period and the as-of time.
Until 0.2.0 adds week_start and quarter_start_month to the policy, the period check is containment only: the week_start weekday is not yet verified.

## Contract 0.2.0 adoption (2026-11-18)

- Every RuleCheck carries `outcome`. Validator rejections are `violation` (unsupported action, inexact or
  unsupported time, punch after `as_of`, duplicate punch time). They are `insufficient_evidence` only when
  the inputs cannot decide: no schedule, unreadable evidence, or totals unavailable.
- Time evidence: with `evidence_ref` None the time must equal the scheduled boundary. With a ref, `new_ts`
  must be within `policy.rules.evidence_tolerance_min` of what the ref names:
  - `schedule_start` / `schedule_end`: the matching boundary of that shift, for an IN or OUT respectively.
  - `note`: a clock time the employee stated, on the work date or the next day. It is parsed with Track B's
    pure `note_times`, so both sides read notes identically.
  - `history_punch`: a same-type, same-weekday history punch's clock time.

  The `missing_punch_window_min` window still bounds every time.
- `as_of`: CaseService and the resolution store set it from the server clock. It is excluded from evidence_version.
  An added punch after `as_of` is a violation. An open trailing clock-in before the scheduled end is
  `insufficient_evidence` (not yet missing) rather than a missing punch.
- Totals: the week must start on `rules.week_start` and the quarter on a `rules.quarter_start_month` boundary.
  The loader derives both periods from the policy.
- Note: a correction backed by evidence but more than `late_tolerance_min` after the scheduled end introduces
  a SCHEDULE_DEVIATION violation, so it is not eligible as-is (tested).
