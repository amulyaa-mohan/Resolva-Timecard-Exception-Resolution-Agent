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

Only the health endpoint and connection page are implemented. No database or AI provider is required yet.
Database migrations, domain contracts, providers, Docker and CI remain assigned work.
This scaffold does not implement authentication, business rules or correction approval.
