# Seeds

Synthetic seed data only: no real employee data, no credentials and no populated database file is
ever committed.

The runnable seed lives in `backend/scripts/seed_demo_week.py`, because it provisions through the
real import and detection path rather than writing rows directly. See
`backend/database/docs/seed_data_guide.md` for what it creates and which exception each day raises.
