"""
Migration Runner for Resolva Database.

Applies SQL DDL migration files (in ascending numerical order) to initialize
or upgrade the SQLite database schema with full foreign-key support.
"""

from pathlib import Path
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_DB_PATH = PROJECT_ROOT.parent / "backend" / "shiftsense.db"


def apply_migrations(db_path: Path = DEFAULT_DB_PATH) -> None:
    """
    Executes all *.sql migration scripts in sequential order against the database.
    """
    print(f"[INFO] Applying migrations to: {db_path.resolve()}")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    migration_files = sorted(BASE_DIR.glob("*.sql"))
    if not migration_files:
        print("[WARN] No SQL migration files found in migrations directory.")
        return

    for sql_file in migration_files:
        print(f"[INFO] Executing migration: {sql_file.name}")
        with open(sql_file, "r", encoding="utf-8") as f:
            script = f.read()
        cursor.executescript(script)
        print(f"  ✓ Successfully executed: {sql_file.name}")

    conn.commit()
    conn.close()
    print("[INFO] All database migrations applied successfully.")


if __name__ == "__main__":
    target_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    apply_migrations(target_path)
