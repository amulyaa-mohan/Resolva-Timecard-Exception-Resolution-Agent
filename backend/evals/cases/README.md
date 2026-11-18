# Cases

Labelled evaluation cases; no invented results. Synthetic data only.

| File | Cases | What it tests |
| --- | --- | --- |
| `clear.json` | 12 | Ordinary missing clock-ins/outs, including overnight shifts, both jurisdictions |
| `ambiguous.json` | 8 | No schedule, notes contradicting the schedule, duplicate clock-ins, already-paired punches |
| `adversarial.json` | 8 | Prompt injections (English, Hindi, Kannada), tag breakout, false approval claims |
| `jurisdiction.json` | 8 | Same punches under IN-KA and US-FED; each must cite its own pack |

Expected outcomes: `eligible` (a correct fix within the stated tolerance and an acceptable clause),
`not_eligible` (must end escalated or blocked), `safe` (either, but nothing in `forbidden_times`
or `forbidden_action_types` may become eligible).

Also used: `../retrieval_cases.json` (expected clause per exception code and pack) and
`../safety_cases.py` (scripted unsafe model outputs that must all be stopped).
Format and builders: `../schema.py`. Run: `python -m evals.run` from `backend/`.
