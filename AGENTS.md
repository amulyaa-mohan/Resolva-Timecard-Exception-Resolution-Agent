# Shared instructions for coding agents

Read `docs/TEAM_RULES.md`, `docs/TASKS.md`, and the latest entries in `UPDATE.md` before making changes. Follow the user's current instructions if they conflict with these files.

## Before work

1. Check the current branch, working tree, and Git author identity. Preserve existing user changes.
2. Fetch remote branches when network access is available. Read teammates' published updates before claiming work. Do not silently switch branches or merge unrelated work.
3. Select a task in `docs/TASKS.md`, assign it to the current developer, and mark it in progress. If another developer owns it, coordinate before changing that scope.
4. Read the relevant contracts and establish dependencies. Do not invent a teammate's interface or claim their unfinished implementation is available.
5. For a new teammate session, ask for their name and track if these are unknown. Never reuse another developer's commit identity.

## During work

- Stay within the claimed task. Shared contract or core changes require a reviewable proposal for the other developer.
- Keep changes small and integration-ready. Use mock boundaries when dependent modules are unfinished.
- Follow the product invariants in `docs/TEAM_RULES.md`.
- Run checks appropriate to the change. Distinguish checks actually run from proposed checks.
- Never commit secrets, real employee data, local databases, or model credentials.

## Before handing off or committing

1. Update the task status, dependencies, and next step in `docs/TASKS.md`.
2. Append a dated entry to `UPDATE.md` using its template. Never rewrite another person's history.
3. Include implementation, tests, task status, and update log in the same commit when committing.
4. Report the branch, changed files, validation, blockers, and next step. State explicitly if changes remain local.
5. Commit or push only when authorized by the user's task. Do not auto-merge or push to a teammate's branch.

An update log is coordination, not a lock or a real-time notification service. A teammate sees changes only after they are published and fetched. Reconcile simultaneous task claims before proceeding.
