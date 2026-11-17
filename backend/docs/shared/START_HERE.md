# Start a shared development session

Give your coding agent this prompt at the beginning of a session:

```text
We are building Resolva with frontend, backend and database teams.
Read root AGENTS.md and route to my area's AGENTS.md, TASKS.md and UPDATE.md using the routing table.
Read backend/docs/shared/TEAM_RULES.md, backend/docs/shared/TASKS.md and backend/docs/shared/CONTRACTS.md.
I am [NAME], working in [frontend/backend/database], on [BRANCH].
For backend I own track [A/B]. Verify my Git identity and existing local changes.
Fetch published team updates if available. Claim an available task with ready dependencies.
Follow ownership boundaries; coordinate contract changes with affected teams.
After work, run relevant checks, update task status and append my area's UPDATE.md.
Report real results, blockers, next step and whether changes are local or published.
Do not commit, push or merge unless I authorize it.
```

For the first session, use SHARED-01 to agree contracts together instead of starting implementation independently.
The root AGENTS.md routes compatible agents to the relevant area; each area also has a discovery pointer. For other tools, explicitly supply the prompt above.
These files instruct agents to maintain updates; they are not a background synchronization service.

## Get the shared files

For a new local clone:

```bash
git clone --branch main https://github.com/amulyaa-mohan/Resolva-Timecard-Exception-Resolution-Agent.git
cd Resolva-Timecard-Exception-Resolution-Agent
```

Select your team's branch after cloning:

```bash
git switch backend
# Frontend contributors: git switch frontend
# Database contributors: git switch database
```

Each shared branch tracks its corresponding remote branch. Fetch before work and reconcile teammates' changes before pushing.
Configure your own author name and verified GitHub email locally:

```bash
git config --local user.name "YOUR NAME"
git config --local user.email "YOUR VERIFIED GITHUB EMAIL OR NOREPLY EMAIL"
```

Do not copy Jayanth's identity. Git commit attribution and the authenticated account used to push are separate; verify both.

## Check published progress

```bash
git fetch origin
git status --short --branch
git branch -r
```

To inspect a team's published updates without merging:

```bash
git show origin/backend:backend/docs/UPDATE.md
git show origin/backend:backend/docs/shared/TASKS.md
```

Use `origin/frontend`, `origin/database`, or `origin/main` to inspect the other branches.
Merge reviewed coordination and implementation changes through the agreed integration branch.
A local UPDATE.md edit is not visible on another machine until published and fetched.
