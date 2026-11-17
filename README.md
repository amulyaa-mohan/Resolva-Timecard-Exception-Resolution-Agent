# Resolva — Timecard Exception Resolution Agent

Resolva helps managers review and resolve attendance issues such as missing
clock-outs, overlapping shifts, missed breaks, and overtime risks.

It combines deterministic attendance rules with policy-grounded AI suggestions.
Each suggestion is validated before a manager approves, edits, or rejects it.
Original attendance records remain unchanged, and every correction is audited.

**AI drafts. Rules verify. The manager decides.**

## What Resolva Does

- Detects six types of timecard exceptions using configurable rules.
- Imports CSV and JSON attendance data into a shared format.
- Retrieves relevant clauses from the employee’s applicable policy version.
- Proposes corrections with supporting evidence and policy citations.
- Escalates cases with missing information or conflicting evidence.
- Supports planned manager queries in English, Kannada, and Hindi.
- Records corrections, approvals, and validation results in an audit trail.

| Exception | What it identifies |
| --- | --- |
| Missing punch | A clock-in or clock-out without its matching event |
| Overlapping shift | Worked shifts that overlap |
| Meal-break breach | Attendance that does not meet configured break rules |
| Overtime risk | Worked and scheduled hours exceeding configured limits |
| Spread-over breach | Excessive time between the first clock-in and last clock-out |
| Schedule deviation | Late arrival, early departure, or an unscheduled shift |

## How It Works

1. **Import attendance:** upload CSV or JSON and review the import preview.
2. **Normalize records:** validate employee IDs, timestamps, and event types.
3. **Detect exceptions:** compare attendance with schedules and policy rules.
4. **Retrieve evidence:** select the applicable policy and supporting clauses.
5. **Generate a proposal:** the AI suggests a structured, evidence-backed action.
6. **Validate the change:** verify citations and rerun the attendance rules.
7. **Review and decide:** a manager approves, edits, rejects, or escalates.
8. **Record the outcome:** save the correction and its complete audit history.

A proposal cannot become eligible for approval simply because the model reports
high confidence. Missing evidence, invalid citations, or failed rules block it.

## Architecture

Resolva uses a modular monolith: one React application, one FastAPI backend,
and local storage for attendance records and searchable policy content.

```mermaid
flowchart TD
    A[CSV / JSON Attendance] --> B[Import and Normalization]
    B --> C[Deterministic Rules Engine]
    C --> D[Policy Resolution and Retrieval]
    D --> E[AI Proposal Provider]
    E --> F[Evidence and Rule Validation]
    F --> G[Manager Review or Escalation]
    G --> H[Correction and Audit Trail]
    I[React Interface] <--> J[FastAPI Backend]
    J --> B
    J --> G
```

| Component | Responsibility | Proposed technology |
| --- | --- | --- |
| Web interface | Exception inbox, evidence, and manager decisions | React, TypeScript, Vite |
| UI components | Accessible forms, tables, and review panels | Tailwind CSS, shadcn/ui |
| Backend | APIs, permissions, and workflow coordination | FastAPI, Pydantic |
| Rules engine | Exception detection and correction validation | Python |
| Database | Attendance, proposals, corrections, and audit events | SQLite, SQLModel |
| Policy retrieval | Version-filtered keyword and semantic search | ChromaDB |
| AI provider | Structured correction proposals | Ollama or Groq |
| Tests | Rule, API, safety, and user-flow verification | pytest, Playwright |

The AI provider cannot directly modify attendance records.
Detection and validation reuse the same rule functions.
Corrections are appended as new records rather than overwriting original punches.

## Install and Run Locally

The runnable scaffold includes a FastAPI health endpoint and a React connection page.
Business workflows, database migrations, and model providers are still to be implemented.

See [Local development](docs/LOCAL_DEVELOPMENT.md) for setup, startup, URLs, and checks.
See [Repository structure](docs/STRUCTURE.md) for module boundaries and team ownership.

Quick setup (Python 3.11+, Node.js 22+):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.lock -e './backend[dev]'
cp .env.example .env
npm --prefix frontend ci --cache ./work/npm-cache
```

Run the API and frontend in separate terminals:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

```bash
npm --prefix frontend run dev
```

Open http://localhost:5173. API documentation is at http://localhost:8000/docs.

## Safety and Scope

Pay-affecting corrections require explicit approval from an authorized manager.
The prototype uses simplified demonstration policies and synthetic records.
It does not calculate or export payroll, certify legal compliance, or include
production HRMS and biometric-device integrations.
