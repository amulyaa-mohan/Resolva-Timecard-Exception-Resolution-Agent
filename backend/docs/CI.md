# CI

Owner: Track B (Amulya Mohan), task B-05. Workflow: `.github/workflows/ci.yml` at the repository root
(GitHub requires that location). It runs on pushes to `main`, `backend`, `frontend` and `database`,
on every pull request, and on manual dispatch.

| Job | Steps | Fails when |
| --- | --- | --- |
| Backend | `ruff check`, `ruff format --check`, `pytest`, `python -m evals.run --gates ci` | lint/format error, any test failure, any CI eval gate failure |
| Frontend | `npm ci`, `npm run build` (TypeScript check + Vite build) | type error or build failure |

The backend eval uses the offline mock provider, so it is deterministic and needs no model or key.
Its CI gates: retrieval top-1 at least 90%, zero wrong-version leakage, 100% harness block rate,
zero unsafe eligible proposals, 100% injection resistance, and every proposal case correct. The
Markdown report appears in the run summary and is uploaded as the `eval-report-mock` artifact.

Real-model evaluations are run locally (`python -m evals.run --provider ollama ... --gates live`)
and committed to `backend/evals/reports/`; CI does not call a model.
