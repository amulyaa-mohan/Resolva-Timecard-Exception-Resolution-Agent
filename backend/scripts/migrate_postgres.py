"""Apply PostgreSQL migrations from backend/database/migrations.

Run from the repository root:
    .venv/bin/python backend/scripts/migrate_postgres.py "$ATTENDANCE_DATABASE_URL"
Only applies files not yet recorded in schema_migrations; refuses edited applied files.
Never point this at a database you do not own.
"""

import argparse

from app.attendance.postgres import apply_migrations

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dsn", help="PostgreSQL connection string")
    applied = apply_migrations(parser.parse_args().dsn)
    print("Applied: " + (", ".join(applied) if applied else "nothing (up to date)"))
