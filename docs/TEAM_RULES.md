# Resolva shared development rules

## Shared objective

Build import → deterministic exception detection → policy-grounded proposal → validation → manager decision → immutable correction and audit.
The first milestone is one employee, one shift, and one missing clock-out resolved end to end.
The repository currently contains documentation; application implementation has not started.

## Ownership

| Track | Developer | Owns |
| --- | --- | --- |
| A — Attendance and resolution | C V Jayanth | Attendance models, imports, six rules, validator, decisions, corrections, audit, database/migrations, authorization dependencies |
| B — Policy and AI | Teammate; name to be recorded | Policy registry, retrieval, providers, proposal pipeline, evidence gates, language intents, application configuration, Docker, CI |
| Shared | Both developers | API contracts, core interfaces, integration tests, architectural decisions |

Each developer owns tests for their modules and reviews the other's changes.
Suggested module boundaries: `backend/app/{attendance,rules,resolution,audit}` for A; `backend/app/{policies,retrieval,ai,language}` for B.
`backend/app/core` and shared schema changes must be coordinated before implementation.
For migration changes, B proposes the model changes and A coordinates migration ordering.
These directories and interfaces are planned, not existing application code.

## Contracts to agree first

- `build_case_context(exception_id) -> CaseContext` — A supplies evidence and its version.
- `resolve_policy(employee_context, work_date) -> PolicySnapshot` — B supplies applicable structured rules and policy identity.
- `generate_proposal(case_context, policy_snapshot) -> ProposalResult` — B returns proposal or escalation.
- `validate_correction(case_context, actions, policy_snapshot) -> ValidationResult` — A supplies shared rule outcomes.
- `record_audit(event) -> AuditEvent` — A supplies append-only history.

Agree field types, error behavior, authorization context, and version semantics together before implementing callers.
B invokes A's validator before returning an eligible proposal; A invokes it again against current evidence at approval.
An escalation must be representable without fabricated citations or actions.

## Product invariants

- AI drafts; deterministic rules verify; an authorized manager decides.
- Raw punches are immutable; corrections and reversals are new audited records.
- Detection and validation reuse the same rules.
- Approval rechecks permissions, evidence freshness, and validation.
- Policy configuration is versioned; retrieval uses the applicable pack and version.
- Citations must exist in retrieved evidence; model confidence cannot override failed checks.
- Missing evidence and provider failures preserve a safe manual-review path.
- Use synthetic data. Demo policies are not a certification of legal compliance.

## Branches and reviews

Use the existing repository; do not create a second repository for coordination.
`main` is the shared integration branch. Merge reviewed changes into it.
`backend` is shared by the two backend developers; `frontend` is shared by frontend developers.
`database` is for database schemas, migrations, and database-related changes, coordinated by track A.
Database contributors agree schema contracts with backend developers before implementation.
Use your own Git author identity on every branch; branch names do not determine attribution.
Before pushing to a shared branch, fetch and integrate teammates' published work without overwriting it.
If a push is rejected, reconcile changes and rerun relevant checks; never force-push to bypass it.
Use task ownership to avoid simultaneous edits. Optional personal feature branches may target the relevant team branch.
Open reviewed PRs from team branches into `main`; do not automatically merge.
GitHub default-branch migration is pending repository-owner action because the current account lacks admin access.
`cv-jayanth` remains temporarily as the existing default branch until the owner changes it to `main`.
Never force-push shared history or overwrite a teammate's changes.
For conflicts in UPDATE.md, preserve both entries. Reconcile conflicting task statuses explicitly.
Documentation updates become shared only after commit/push and integration or direct branch inspection.

## Definition of done

- The task's acceptance check passes, or any limitation is stated explicitly.
- Relevant tests/checks have been run and their actual outcomes recorded.
- Interfaces and setup documentation reflect the implementation.
- TASKS.md and UPDATE.md are updated in the same change.
- Changes are reviewed before integration; blocked or untested work is not marked done.
