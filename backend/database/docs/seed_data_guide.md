# Resolva Seed Data Guide

All seed data is synthetic. No real employee data, and no populated database file, is ever
committed. Credentials are written to the git-ignored `backend/local/`.

```bash
.venv/bin/python backend/scripts/seed_demo_week.py "postgresql://user@host:5432/resolva"
```

The script migrates first, then provisions through the **real** import path: it previews and commits
CSV exactly as the API does, and lets the detection job raise the exceptions. Nothing is written
straight into `exceptions`, so the seed exercises the same code a demo does.

## 1. Organisational reference data

| Table | Rows |
| --- | --- |
| `organizations` | 1 (`ORG-DEMO`) |
| `locations` | 1 (`BLR-DEMO`, Bengaluru, Asia/Kolkata) |
| `managers` | 1 (`M-DEMO-1`), with a 24-hour bearer credential |

## 2. Policy packs

Not seeded into the database. Policy packs are versioned YAML under `backend/policies/`
(`IN-KA@2025.1`, `US-FED@2025.1`), owned by Track B. Rows record `pack@version` as text, so a
decision stays reconstructable without the database holding policy text.

## 3. Employee roster

| Employee | Name | Why they exist |
| --- | --- | --- |
| `E-DEMO-1` | Aarav Sharma | a clean day plus three exception types |
| `E-DEMO-2` | Diya Nair | the long day: spread-over and overtime |
| `E-DEMO-3` | Rohan Gupta | the overlapping session |

Names, job titles and pay types are display data. Detection and validation are tested with all of
them null.

## 4. Shifts, punches and the exceptions they raise

Last week is used, so every day is finished and its evidence is final.

| Employee | Day | Punches | Raises |
| --- | --- | --- | --- |
| E-DEMO-1 | Mon | 09:00, break 13:00-14:00, 18:00 | nothing (the control case) |
| E-DEMO-1 | Tue | 09:00, break 13:00-14:00 | `MISSING_PUNCH` |
| E-DEMO-1 | Wed | 09:00, 18:00 | `MEAL_BREAK_BREACH` |
| E-DEMO-1 | Fri | 09:25, break 13:00-14:00, 18:00 | `SCHEDULE_DEVIATION` (tolerance is 7 min) |
| E-DEMO-2 | Wed | 06:00 to 18:30 with two breaks | `SPREAD_OVER_BREACH` and `OVERTIME_RISK` |
| E-DEMO-3 | Thu | 09:00, 10:00, 17:00, 18:00 | `OVERLAPPING_SHIFT` |

All six exception types, plus one day that correctly raises nothing.

## 5. Prior totals

The script also writes `day_totals` from the quarter start to yesterday: 8 h weekdays, marked
complete. Without them the overtime rule is correctly undecidable, because one week of punches
cannot establish a weekly or quarterly limit. A real deployment loads these from payroll history.

## 6. Two behaviours worth knowing in a demo

- **An unpairable day makes that employee's week unknown.** A missing punch or an overlap means the
  week's hours cannot be computed, so other cases for that employee escalate on overtime until it is
  resolved. That is why the overlap case has its own employee. Resolving the missing punch makes its
  week decidable again.
- **Re-running the seed is safe.** Punches deduplicate on `(source, source_event_id)`, exception ids
  are deterministic, and existing credentials are reused rather than overwritten.
