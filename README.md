# Resolva - Timecard Exception Resolution Agent

Resolva is a deterministic-first, human-in-the-loop Timecard Exception Resolution Agent for enterprise HCM & Payroll teams. It detects shift, punch, meal-break, spread-over, and overtime exceptions against versioned jurisdiction policy packs (`IN-KA@2025.1`, `US-FED+CA@2025.1`), generates policy-cited proposals using open-weight LLMs, validates every proposed action deterministically, and enforces manager sign-off with an append-only audit trail.

## Quick Start
- Frontend: `npm --prefix frontend install && npm --prefix frontend run dev` (http://localhost:5173)
- Backend: `python -m pip install -r backend/requirements.txt && uvicorn app.main:app --app-dir backend --reload --port 8000`
- Shortcuts: `J/K` navigate, `A` approve, `E` edit, `R` reject, `Esc` close.

## Open-Weight Model Licences
- Primary Proposal Model (`Qwen/Qwen2.5-7B-Instruct`): Apache License 2.0
- Fallback Model (`meta-llama/Llama-3.1-8B-Instruct`): Llama 3.1 Community License

## Demo Video
- 10-Minute Walkthrough: (Link to be added after recording)
