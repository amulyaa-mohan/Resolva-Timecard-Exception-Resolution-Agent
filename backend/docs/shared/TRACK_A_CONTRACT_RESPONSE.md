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
