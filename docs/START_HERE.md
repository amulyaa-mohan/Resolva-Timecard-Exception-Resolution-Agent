# Start a shared development session

Give your coding agent this prompt at the beginning of a session:

```text
We are building Resolva in this repository with two backend developers.
Read AGENTS.md, docs/TEAM_RULES.md, docs/TASKS.md, and UPDATE.md first.
Check my branch and Git identity, and fetch published teammate updates if possible.
I am [YOUR NAME], working on track [A or B], on branch [YOUR BRANCH].
Select the next unclaimed task in my track whose dependencies are ready.
Before coding, record the task claim and explain the acceptance check.
Follow the shared contracts and preserve the other developer's work.
After changes, run relevant checks, update docs/TASKS.md, and append UPDATE.md.
Report what changed, actual test results, blockers, and the next integration step.
Do not commit or push unless I authorize it. Do not merge automatically.
```

For the first session, use SHARED-01 to agree contracts together instead of starting implementation independently.
AGENTS.md is automatically read by compatible coding agents. For other tools, explicitly supply the prompt above.
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
git show origin/backend:UPDATE.md
git show origin/backend:docs/TASKS.md
```

Use `origin/frontend`, `origin/database`, or `origin/main` to inspect the other branches.
Merge reviewed coordination and implementation changes through the agreed integration branch.
A local UPDATE.md edit is not visible on another machine until published and fetched.
