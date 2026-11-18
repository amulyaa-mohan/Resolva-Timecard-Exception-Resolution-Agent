"""Append-only audit events with a SHA-256 hash chain (demo SQLite store).

Callers append inside their own transaction, so an audit event commits or rolls back
together with the decision it describes. Triggers reject UPDATE and DELETE; the hash
chain makes any out-of-band edit detectable with verify_chain.
"""

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    occurred_at TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('manager', 'system', 'ai')),
    actor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    exception_id TEXT NOT NULL,
    decision_id TEXT,
    payload_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS audit_events_exception ON audit_events(exception_id, seq);
CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
"""

_FIELDS = (
    "event_id",
    "occurred_at",
    "actor_type",
    "actor_id",
    "event_type",
    "exception_id",
    "decision_id",
    "payload_json",
    "prev_hash",
)


def _digest(record: dict[str, Any]) -> str:
    body = json.dumps({k: record[k] for k in _FIELDS}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def append_event(
    connection: sqlite3.Connection,
    *,
    actor_type: str,
    actor_id: str,
    event_type: str,
    exception_id: str,
    payload: dict[str, Any],
    decision_id: str | None = None,
    occurred_at: datetime | None = None,
) -> str:
    """Append one event in the caller's open transaction and return its id."""
    row = connection.execute("SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
    record = {
        "event_id": f"AUD-{uuid.uuid4().hex}",
        "occurred_at": (occurred_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "actor_type": actor_type,
        "actor_id": actor_id,
        "event_type": event_type,
        "exception_id": exception_id,
        "decision_id": decision_id,
        "payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
        "prev_hash": row[0] if row else GENESIS,
    }
    record["hash"] = _digest(record)
    connection.execute(
        f"INSERT INTO audit_events ({', '.join((*_FIELDS, 'hash'))}) "
        f"VALUES ({', '.join('?' * (len(_FIELDS) + 1))})",
        tuple(record[k] for k in (*_FIELDS, "hash")),
    )
    return record["event_id"]


def events_for_exception(connection: sqlite3.Connection, exception_id: str) -> list[dict]:
    rows = connection.execute(
        f"SELECT {', '.join((*_FIELDS, 'hash'))} FROM audit_events "
        "WHERE exception_id=? ORDER BY seq",
        (exception_id,),
    ).fetchall()
    events = []
    for row in rows:
        record = dict(zip((*_FIELDS, "hash"), row, strict=True))
        record["payload"] = json.loads(record.pop("payload_json"))
        events.append(record)
    return events


def verify_chain(connection: sqlite3.Connection) -> bool:
    """True when every event links to its predecessor and matches its own hash."""
    previous = GENESIS
    query = f"SELECT {', '.join((*_FIELDS, 'hash'))} FROM audit_events ORDER BY seq"
    for row in connection.execute(query):
        record = dict(zip((*_FIELDS, "hash"), row, strict=True))
        if record["prev_hash"] != previous or _digest(record) != record["hash"]:
            return False
        previous = record["hash"]
    return True
