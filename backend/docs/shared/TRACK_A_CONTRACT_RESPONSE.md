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
