# Run the development scaffold

Prerequisites: Python 3.11+ and Node.js 22+ with npm.
Run from the repository root. Backend uses port 8000 and frontend uses 5173.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.lock -e './backend[dev]'
cp backend/.env.example backend/.env
npm --prefix frontend ci --cache ./work/npm-cache
```

Start the API in one terminal:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the web app in another terminal:

```bash
npm --prefix frontend run dev
```

Open http://localhost:5173 and check the connection indicator.
API docs: http://localhost:8000/docs. Health: http://localhost:8000/health.
Vite proxies `/api` to the local backend. Stop both processes with Ctrl+C.

```bash
.venv/bin/python -m pytest backend/tests
.venv/bin/python -m ruff check backend
npm --prefix frontend run build
```

Only the health endpoint and connection page are exposed over HTTP. No database or model is required:
the default `LLM_PROVIDER=mock` runs offline. Set `AI_ENABLED=false` in backend/.env for rules-only mode.
Database migrations, domain routes and CI (B-05) remain assigned work.

Windows (Git Bash): use `python -m venv venv` and `venv/Scripts/python.exe` in place of `.venv/bin/python`.

Backend container (needs Docker Desktop running):

```bash
cd backend
docker compose up --build
```

Real model, local and offline (Ollama in Docker; about 5 GB of models, pulled once):

```bash
cd backend
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d ollama   # NVIDIA GPU
# or without a GPU: docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b-instruct
docker compose exec ollama ollama pull nomic-embed-text
python scripts/live_check.py --provider ollama --embeddings ollama
```

The first request after Ollama starts loads the model into memory and takes 30-60 s (measured on
an RTX 5060 laptop), far beyond the 8 s budget, so it escalates. Run `live_check.py` once before a
demo to warm the models; Resolva asks Ollama to keep them loaded for 30 minutes.

On Windows, call the API at `http://127.0.0.1:8000` rather than `localhost`: resolving `localhost`
tries IPv6 first and adds about 2 s to every request from Python/HTTP clients.

Then set `LLM_PROVIDER=ollama` (and optionally `EMBEDDING_PROVIDER=ollama`) in backend/.env.

Evaluation (from backend/): `python -m evals.run` (offline, CI gates) or
`python -m evals.run --provider ollama --embeddings ollama --gates live` (real model; writes
`evals/reports/`). See backend/docs/CI.md.
Hosted alternative: put `GROQ_API_KEY` in backend/.env and set `LLM_PROVIDER=groq`.
`/health` reports `llm_status` and `mode` (`ai_assisted` or `rules_only`).
This scaffold does not implement authentication, business rules or correction approval.
