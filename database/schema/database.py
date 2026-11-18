"""
Database Configuration for Resolva – Timecard Exception Resolution Agent.

This module configures the SQLite database (`shiftsense.db`), creates the SQLModel
engine, provides the table initialization function (`create_db_and_tables`), and
defines the database session dependency (`get_session`) for FastAPI endpoints.
"""

import sys
from pathlib import Path
from typing import Annotated, Generator
from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

# ------------------------------------------------------------------------------
# 1. Project Path Setup
# ------------------------------------------------------------------------------
# Ensure the 'backend' folder is in Python's module search path so 'app' and 'models'
# packages can be imported cleanly from any working directory.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ------------------------------------------------------------------------------
# 2. SQLite Database Configuration
# ------------------------------------------------------------------------------
# Database file name as required: 'shiftsense.db'
DATABASE_FILENAME = "shiftsense.db"

# Store the database file directly inside the 'backend' folder
DATABASE_PATH = BASE_DIR / DATABASE_FILENAME

# SQLite database connection URL
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# 'check_same_thread: False' is required for SQLite when running with FastAPI
# because requests may be processed across multiple threads.
connect_args = {"check_same_thread": False}

# Create the SQLModel engine
# 'echo=True' logs generated SQL queries to the console for easy debugging.
engine = create_engine(
    DATABASE_URL,
    echo=True,
    connect_args=connect_args,
)


# ------------------------------------------------------------------------------
# 3. Database Table Initialization Hook
# ------------------------------------------------------------------------------
def create_db_and_tables() -> None:
    """
    Creates all database tables registered in SQLModel metadata inside 'shiftsense.db'.

    This function is executed during FastAPI application startup. All models
    defined in 'app.models' and 'models' are imported so they register with
    SQLModel.metadata and are automatically created in the SQLite database.
    """
    # Import model packages so all defined models register with SQLModel.metadata
    import app.models  # noqa: F401
    try:
        import models  # noqa: F401
    except ImportError:
        pass

    # Create all tables registered in SQLModel's metadata
    SQLModel.metadata.create_all(engine)


# ------------------------------------------------------------------------------
# 4. FastAPI Database Session Dependency
# ------------------------------------------------------------------------------
def get_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides an active SQLModel database session per request.

    Uses a context manager (`with Session(engine)`) to guarantee that the session
    is properly closed after each request completes, preventing connection leaks.
    """
    with Session(engine) as session:
        yield session


# Type alias for cleaner route signatures using FastAPI dependency injection.
# Example usage in a route:
#   @app.post("/timecards")
#   def create_timecard(timecard: Timecard, session: SessionDep):
#       session.add(timecard)
#       session.commit()
SessionDep = Annotated[Session, Depends(get_session)]


if __name__ == "__main__":
    # Allows initializing the database directly via `python database.py`
    print(f"[INFO] Initializing database at: {DATABASE_PATH}")
    create_db_and_tables()
    print("[INFO] Database initialization complete.")
