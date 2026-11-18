"""
Shift Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `Shift` SQLModel database table, representing planned
or scheduled work shifts assigned to employees against which actual timecard
punch records are compared to detect deviations and exceptions.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from pydantic import model_validator
from sqlalchemy import CheckConstraint, DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .employee import Employee


# ------------------------------------------------------------------------------
# Shift Database Model
# ------------------------------------------------------------------------------
class Shift(SQLModel, table=True):
    """
    Represents a scheduled work shift for an employee.

    Attributes:
        id: Unique identifier for the shift (auto-generated primary key).
        employee_id: Foreign key referencing the employee assigned to the shift ('employee.id').
        start: Scheduled start date and time of the shift (required datetime).
        end: Scheduled end date and time of the shift (required datetime, must be > start).
        planned_break_min: Planned unpaid break duration in minutes (defaults to 0, must be >= 0).
    """
    # Explicit table name matching foreign key conventions
    __tablename__ = "shift"

    # Database-level check constraints for SQLite and SQL engines
    __table_args__ = (
        CheckConstraint("end > start", name="check_shift_end_after_start"),
        CheckConstraint("planned_break_min >= 0", name="check_planned_break_min_non_negative"),
    )

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the shift",
    )

    # Required foreign key referencing employee.id
    employee_id: int = Field(
        foreign_key="employee.id",
        nullable=False,
        index=True,
        description="Foreign key referencing employee.id",
    )

    # Required scheduled shift start datetime (supports both naive and UTC timezone datetimes)
    start: datetime = Field(
        sa_type=DateTime,
        nullable=False,
        index=True,
        description="Scheduled shift start timestamp (required)",
    )

    # Required scheduled shift end datetime (supports both naive and UTC timezone datetimes)
    end: datetime = Field(
        sa_type=DateTime,
        nullable=False,
        index=True,
        description="Scheduled shift end timestamp (required, must be after start)",
    )

    # Planned break duration in minutes, defaults to 0 and cannot be negative
    planned_break_min: int = Field(
        default=0,
        nullable=False,
        ge=0,
        description="Planned break time in minutes (defaults to 0, cannot be negative)",
    )

    # --------------------------------------------------------------------------
    # Python & Pydantic Validation
    # --------------------------------------------------------------------------
    @model_validator(mode="after")
    def validate_shift_constraints(self):
        """
        Validates that:
        1. Shift end time is strictly later than start time.
        2. Planned break minutes is non-negative.
        """
        if self.start and self.end:
            start_tz = self.start.tzinfo
            end_tz = self.end.tzinfo
            if (start_tz is None) != (end_tz is None):
                s = self.start.replace(tzinfo=timezone.utc) if start_tz is None else self.start
                e = self.end.replace(tzinfo=timezone.utc) if end_tz is None else self.end
            else:
                s, e = self.start, self.end

            if e <= s:
                raise ValueError("Shift 'end' must be later than 'start'")

        if self.planned_break_min is not None and self.planned_break_min < 0:
            raise ValueError("planned_break_min cannot be negative")
        return self

    def __init__(self, **data):
        """
        Constructor validation to ensure constraints are enforced during direct instantiation.
        """
        super().__init__(**data)
        if self.start and self.end:
            start_tz = self.start.tzinfo
            end_tz = self.end.tzinfo
            if (start_tz is None) != (end_tz is None):
                s = self.start.replace(tzinfo=timezone.utc) if start_tz is None else self.start
                e = self.end.replace(tzinfo=timezone.utc) if end_tz is None else self.end
            else:
                s, e = self.start, self.end

            if e <= s:
                raise ValueError("Shift 'end' must be later than 'start'")

        if self.planned_break_min is not None and self.planned_break_min < 0:
            raise ValueError("planned_break_min cannot be negative")

    # --------------------------------------------------------------------------
    # Future Relationships (to be activated when full relationship graph is wired)
    # --------------------------------------------------------------------------
    # employee: Optional["Employee"] = Relationship(back_populates="shifts")
