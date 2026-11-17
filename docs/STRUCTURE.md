# Repository structure

- `backend/app`: FastAPI entry point and track A/B module packages.
- `backend/tests`: health smoke test plus unit, integration and contract boundaries.
- `frontend`: React/TypeScript/Vite starter; frontend team owns UI implementation.
- `database`: schema design, ordered migrations and synthetic seed ownership.
- `policies`, `prompts`: versioned policy sources and prompt templates.
- `data/fixtures`: import test data.
- `evals`: labeled cases and measured reports.
- `docs/adr`: architecture decisions.
- `scripts`, `.github/workflows`: reserved developer tooling and CI.

README files preserve unimplemented directories in Git and describe their purpose.
They are not claims of finished functionality. See LOCAL_DEVELOPMENT.md for runnable setup.

- `backend/docs/AGENTS.md`: canonical coding-agent instructions.
- `backend/docs/UPDATE.md`: shared append-only progress log.
- Root `AGENTS.md`: discovery pointer to the backend instructions.
