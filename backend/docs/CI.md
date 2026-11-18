# CI

Owner: Track B (Amulya Mohan), task B-05. Workflow: `.github/workflows/ci.yml` at the repository root
(GitHub requires that location). It runs on pushes to `main`, `backend`, `frontend` and `database`,
on every pull request, and on manual dispatch.

| Job | Steps | Fails when |
| --- | --- | --- |
| Backend | `ruff check`, `ruff format --check`, `pytest` (with a `postgres:15` service), PostgreSQL-tests-ran guard, `python -m evals.run --gates ci` | lint/format error, any test failure, any PostgreSQL test skipped, any CI eval gate failure |
| Frontend | `npm ci`, `npm run build` (TypeScript check + Vite build) | type error or build failure |

The backend job starts a disposable `postgres:15` service (trust auth, CI only) and sets
`TEST_DATABASE_URL=postgresql://postgres@localhost:5432/resolva_test`; it installs
`.[dev,postgres]`. Track A's PostgreSQL tests skip without that variable, so a guard step fails the
build if any of them were skipped.

The backend eval uses the offline mock provider, so it is deterministic and needs no model or key.
Its CI gates: retrieval top-1 at least 90%, zero wrong-version leakage, 100% harness block rate,
zero unsafe eligible proposals and 100% injection resistance under both the real (Track A) and
stand-in validators, every proposal case correct under the real validator, and every
evidence-gap case (`evals/cases/evidence.json`) handled correctly. The
Markdown report appears in the run summary and is uploaded as the `eval-report-mock` artifact.

Real-model evaluations are run locally (`python -m evals.run --provider ollama ... --gates live`)
and committed to `backend/evals/reports/`; CI does not call a model.
