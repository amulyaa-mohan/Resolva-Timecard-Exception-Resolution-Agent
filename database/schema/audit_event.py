"""
Audit Event Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `AuditEvent` SQLModel database table, providing an immutable,
append-only audit trail of all actions performed by users, the system, and AI agents.
It captures before/after states, correlation trace IDs, and actor attributions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import model_validator
from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, SQLModel


def get_utc_now() -> datetime:
    """
    Returns the current date and time in UTC.
    Used as the default_factory for timestamp fields.
    """
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------
# Audit Actor Enumeration & Allowed Values
# ------------------------------------------------------------------------------
class AuditActor(str, Enum):
    """
    Standard actor classifications responsible for an audit event.

    - USER: Human actor (e.g., employee, supervisor, HR/payroll admin).
    - SYSTEM: Automated scheduled job, background task, or deterministic rule engine.
    - AI: Autonomous AI agent or LLM resolution pipeline.
    """
    USER = "user"
    SYSTEM = "system"
    AI = "ai"


ALLOWED_ACTORS = {"user", "system", "ai"}


# ------------------------------------------------------------------------------
# AuditEvent Database Model
# ------------------------------------------------------------------------------
class AuditEvent(SQLModel, table=True):
    """
    Represents an immutable, append-only audit event log entry.

    In compliance with governance and payroll auditing requirements, audit records
    are strictly append-only; update and delete operations should not be performed.

    Attributes:
        id: Unique identifier for the audit event (auto-generated primary key).
        actor: Entity performing the action ('user', 'system', or 'ai', or prefixed e.g. 'user:123').
        action: Identifier of the operation performed (e.g., 'PROPOSAL_GENERATED', 'CORRECTION_APPLIED').
        entity_ref: Reference to the target entity (e.g., 'exception:10', 'proposal:4', 'punch:105').
        before: Optional JSON-compatible data representing state prior to action.
        after: Optional JSON-compatible data representing state following action.
        trace_id: Distributed correlation trace ID linking related audit entries.
        ts: Timestamp when the event occurred (defaults to current UTC time).
    """
    # Explicit table name matching SQL conventions
    __tablename__ = "audit_event"

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the audit event record",
    )

    # Required actor classification ('user', 'system', or 'ai')
    actor: str = Field(
        nullable=False,
        index=True,
        description="Actor performing the action ('user', 'system', or 'ai')",
    )

    # Required action name
    action: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=100,
        description="Action performed (e.g. 'EXCEPTION_DETECTED', 'PROPOSAL_APPLIED')",
    )

    # Required entity reference string
    entity_ref: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=255,
        description="Reference identifier of affected entity (e.g., 'exception:1', 'correction:5')",
    )

    # Optional JSON-compatible snapshot of state before the action
    before: Optional[Any] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Snapshot of entity state before the action was executed (optional JSON)",
    )

    # Optional JSON-compatible snapshot of state after the action
    after: Optional[Any] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Snapshot of entity state after the action was executed (optional JSON)",
    )

    # Required correlation trace ID linking events across distributed operations
    trace_id: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=128,
        description="Distributed tracing identifier linking related lifecycle events",
    )

    # Creation timestamp defaulting to current UTC time
    ts: datetime = Field(
        default_factory=get_utc_now,
        sa_type=DateTime,
        nullable=False,
        index=True,
        description="Timestamp when the audit event occurred (UTC)",
    )

    # --------------------------------------------------------------------------
    # Pydantic & Constructor Validation
    # --------------------------------------------------------------------------
    @model_validator(mode="after")
    def validate_audit_fields(self):
        """
        Validates actor against allowed actor categories ('user', 'system', 'ai').
        """
        if self.actor is not None:
            raw_actor = self.actor.value if isinstance(self.actor, Enum) else str(self.actor)
            base_actor = raw_actor.split(":")[0].strip().lower()
            if base_actor not in ALLOWED_ACTORS:
                raise ValueError(
                    f"Invalid actor '{raw_actor}'. Must be 'user', 'system', or 'ai' (or prefixed e.g. 'user:id')."
                )
        return self

    def __init__(self, **data):
        """
        Constructor validation to ensure constraints are enforced during direct instantiation.
        """
        super().__init__(**data)
        if hasattr(self, "actor") and self.actor is not None:
            raw_actor = self.actor.value if isinstance(self.actor, Enum) else str(self.actor)
            base_actor = raw_actor.split(":")[0].strip().lower()
            if base_actor not in ALLOWED_ACTORS:
                raise ValueError(
                    f"Invalid actor '{raw_actor}'. Must be 'user', 'system', or 'ai' (or prefixed e.g. 'user:id')."
                )
