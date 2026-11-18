"""
Correction Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `Correction` SQLModel database table, representing applied
adjustments, punch additions, or policy resolutions.
In accordance with audit and compliance standards, raw punches remain immutable,
and all adjustments are recorded as new, append-only `Correction` records.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional
from pydantic import model_validator
from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .proposal import Proposal


def get_utc_now() -> datetime:
    """
    Returns the current date and time in UTC.
    Used as the default_factory for timestamp fields.
    """
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------
# Correction Database Model
# ------------------------------------------------------------------------------
class Correction(SQLModel, table=True):
    """
    Represents an applied timecard adjustment or exception correction.

    In compliance with audit requirements, raw punch records are immutable;
    any adjustments, inserted punches, or approved deviations are captured
    as discrete, append-only Correction records.

    Attributes:
        id: Unique identifier for the correction (auto-generated primary key).
        proposal_id: Optional foreign key referencing the source proposal ('proposal.id').
                     Can be NULL for direct manual adjustments.
        actions: Required JSON-compatible list of applied correction actions.
        applied_by: Required identifier of the person (e.g., manager ID) or system applying the correction.
        reason_code: Required classification reason code (e.g., 'MISSED_PUNCH_INSERTED', 'OVERTIME_APPROVED').
        comment: Optional human-readable notes or justification.
        ts: Timestamp when the correction was applied (defaults to current UTC time).
    """
    # Explicit table name matching SQL conventions
    __tablename__ = "correction"

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the correction record",
    )

    # Optional foreign key referencing proposal.id (can be NULL for manual supervisor adjustments)
    proposal_id: Optional[int] = Field(
        default=None,
        foreign_key="proposal.id",
        nullable=True,
        index=True,
        description="Optional foreign key referencing proposal.id (NULL for direct manual corrections)",
    )

    # Required JSON-compatible list of applied actions
    actions: List[Any] = Field(
        sa_column=Column(JSON, nullable=False),
        description="Required JSON-compatible list of applied correction actions",
    )

    # Required identifier of the person or system applying the correction
    applied_by: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=100,
        description="Identifier of the user or system component applying the correction",
    )

    # Required business reason classification code
    reason_code: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=50,
        description="Standardized reason code explaining why the correction was applied",
    )

    # Optional human-readable notes or comments
    comment: Optional[str] = Field(
        default=None,
        nullable=True,
        description="Optional notes, manager justification, or review commentary",
    )

    # Timestamp defaulting to current UTC time
    ts: datetime = Field(
        default_factory=get_utc_now,
        sa_type=DateTime,
        nullable=False,
        index=True,
        description="Timestamp when the correction was recorded (UTC)",
    )

    # --------------------------------------------------------------------------
    # Pydantic & Constructor Validation
    # --------------------------------------------------------------------------
    @model_validator(mode="after")
    def validate_correction_fields(self):
        """
        Validates that actions is a list.
        """
        if self.actions is not None and not isinstance(self.actions, list):
            raise ValueError("actions must be a list of correction actions")
        return self

    def __init__(self, **data):
        """
        Constructor validation to ensure constraints are enforced during direct instantiation.
        """
        super().__init__(**data)
        if hasattr(self, "actions") and self.actions is not None:
            if not isinstance(self.actions, list):
                raise ValueError("actions must be a list of correction actions")

    # --------------------------------------------------------------------------
    # Future Relationships (to be activated when full relationship graph is wired)
    # --------------------------------------------------------------------------
    # proposal: Optional["Proposal"] = Relationship(back_populates="corrections")
