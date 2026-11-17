# Resolva shared development rules

## Shared objective

Build import → deterministic exception detection → policy-grounded proposal → validation → manager decision → immutable correction and audit.
The first milestone is one employee, one shift, and one missing clock-out resolved end to end.
The repository now includes a runnable health/API and frontend scaffold; business implementation remains pending.

## Ownership

| Track | Developer | Owns |
| --- | --- | --- |
| A — Attendance and resolution | C V Jayanth | Attendance models, imports, six rules, validator, decisions, corrections, audit, database/migrations, authorization dependencies |
| B — Policy and AI | Teammate; name to be recorded | Policy registry, retrieval, providers, proposal pipeline, evidence gates, language intents, application configuration, Docker, CI |
| Shared | Both developers | API contracts, core interfaces, integration tests, architectural decisions |

Each developer owns tests for their modules and reviews the other's changes.
Suggested module boundaries: `backend/app/{attendance,rules,resolution,audit}` for A; `backend/app/{policies,retrieval,ai,language}` for B.
`backend/app/core` and shared schema changes must be coordinated before implementation.
Database contributors own migration ordering; track A coordinates backend compatibility and track B proposes its policy/proposal model requirements.
The module directories are scaffolded; the business interfaces still require joint agreement.

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
`main` is the GitHub default branch. The obsolete `cv-jayanth` branch has been removed.
Never force-push shared history or overwrite a teammate's changes.
For conflicts in any area UPDATE.md, preserve both entries. Reconcile conflicting task statuses explicitly.
Documentation updates become shared only after commit/push and integration or direct branch inspection.

## Definition of done

- The task's acceptance check passes, or any limitation is stated explicitly.
- Relevant tests/checks have been run and their actual outcomes recorded.
- Interfaces and setup documentation reflect the implementation.
- The relevant area task tracker and UPDATE.md are updated in the same change.
- Changes are reviewed before integration; blocked or untested work is not marked done.

## Area instruction routing

- Frontend: frontend/docs/AGENTS.md, BUILD_PLAN.md, TASKS.md and UPDATE.md.
- Backend: backend/docs/AGENTS.md, TASKS.md and UPDATE.md.
- Database: database/docs/AGENTS.md, TASKS.md and UPDATE.md.
- Shared contracts: docs/CONTRACTS.md; shared milestones: docs/TASKS.md.

Frontend owns UI and client integration; database owns schema/migrations/seeds in coordination with backend.
No team should implement another team's missing functionality by silently crossing ownership boundaries.
