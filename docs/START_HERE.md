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
git clone --branch cv-jayanth https://github.com/amulyaa-mohan/Resolva-Timecard-Exception-Resolution-Agent.git
cd Resolva-Timecard-Exception-Resolution-Agent
```

The teammate should then create their own branch from this shared starting point:

```bash
git switch -c YOUR-NAME-backend
```

Replace YOUR-NAME before running. Configure your own author name and verified GitHub email locally:

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

To inspect Jayanth's published updates without merging:

```bash
git show origin/cv-jayanth:UPDATE.md
git show origin/cv-jayanth:docs/TASKS.md
```

Use the equivalent remote branch for the teammate after it is published.
Merge reviewed coordination and implementation changes through the agreed integration branch.
A local UPDATE.md edit is not visible on another machine until published and fetched.
