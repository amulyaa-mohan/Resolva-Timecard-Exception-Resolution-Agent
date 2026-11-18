"""Database integrity checks and model-text retention (DB-04).

Run from the repository root:
    .venv/bin/python backend/scripts/db_maintenance.py verify "$DSN"
    .venv/bin/python backend/scripts/db_maintenance.py purge-traces "$DSN" --older-than-days 30

`verify` exits 1 when it finds a problem, so it can run in a scheduled job. Notices are
reported but do not fail the run. `purge-traces` deletes only the model's raw text; the trace
rows and every audit event stay untouched.
"""

import argparse
import sys

from app.attendance.maintenance import purge_raw_outputs, verify
from app.attendance.postgres import PostgresBackend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("verify", help="report invariants no constraint can enforce")
    check.add_argument("dsn")
    purge = commands.add_parser("purge-traces", help="remove model text past its retention window")
    purge.add_argument("dsn")
    purge.add_argument("--older-than-days", type=int, default=30)
    purge.add_argument(
        "--apply", action="store_true", help="actually delete; without it, only report the count"
    )
    arguments = parser.parse_args(argv)
    backend = PostgresBackend(arguments.dsn)

    if arguments.command == "verify":
        with backend.transaction(immediate=False) as connection:
            findings = verify(connection)
        for finding in findings:
            print(finding)
        problems = [f for f in findings if f.level == "problem"]
        print(
            f"{len(problems)} problem(s), {len(findings) - len(problems)} notice(s)."
            if findings
            else "No problems found."
        )
        return 1 if problems else 0

    with backend.transaction() as connection:
        affected = purge_raw_outputs(
            connection,
            older_than_days=arguments.older_than_days,
            dry_run=not arguments.apply,
        )
    if arguments.apply:
        print(f"Removed raw text from {affected} trace(s).")
    else:
        print(f"Would remove raw text from {affected} trace(s). Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
