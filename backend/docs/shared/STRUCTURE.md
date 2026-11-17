# Repository structure

```text
frontend/
  src/             React UI and API client
  tests/           UI tests
  docs/            Frontend agent rules, build plan and updates
backend/
  app/             FastAPI and domain modules
  tests/           Backend tests
  database/        Schemas, migrations, seeds and database agent docs
  policies/        Policy packs
  prompts/         AI prompt templates
  data/            Synthetic import fixtures
  evals/           Evaluation cases and reports
  scripts/         Developer tooling
  docs/            Backend rules and updates
    shared/        Team coordination, contracts and local setup
  .env.example     Backend configuration template
```

Root contains README.md, the AGENTS.md discovery pointer, and .gitignore.
GitHub Actions workflows, when implemented, must use GitHub's required root `.github/workflows/` location.
The former placeholder is now backend/docs/CI.md; there is no active CI workflow yet.
Business modules remain scaffolds. See LOCAL_DEVELOPMENT.md for working startup instructions.
