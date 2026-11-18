"""
Punch Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `Punch` SQLModel database table, representing raw timecard
punch events recorded by employees (clock in, clock out, break start, break end).

Design Note on Immutability:
Raw punches represent an immutable, append-only event log capturing the exact time
and source of employee clock actions. They must never be updated or deleted in place.
Any corrections or exception resolutions should create separate resolution events,
preserving the raw punch history for auditing and compliance.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .employee import Employee


# ------------------------------------------------------------------------------
# 1. Punch Enums
# ------------------------------------------------------------------------------
class PunchType(str, Enum):
    """
    Allowed punch event types for employee time tracking.

    - IN: Clocking in at the start of a work period.
    - OUT: Clocking out at the conclusion of a work period.
    - BREAK_START: Beginning an unpaid/paid rest or meal break.
    - BREAK_END: Concluding a rest or meal break.
    """
    IN = "in"
    OUT = "out"
    BREAK_START = "break_start"
    BREAK_END = "break_end"


class PunchSource(str, Enum):
    """
    Allowed origin sources from which the timecard punch was recorded.

    - KIOSK: Physical on-site terminal, badge reader, or biometric kiosk.
    - MOBILE: Mobile device application with GPS or geofencing capability.
    - WEB: Web browser employee self-service portal.
    """
    KIOSK = "kiosk"
    MOBILE = "mobile"
    WEB = "web"


# ------------------------------------------------------------------------------
# 2. Punch Database Model
# ------------------------------------------------------------------------------
class Punch(SQLModel, table=True):
    """
    Represents an immutable raw clock event recorded for an employee.

    Attributes:
        id: Unique identifier for the punch (auto-generated primary key).
        employee_id: Foreign key referencing the employee who clocked ('employee.id').
        ts: Timestamp when the clock event occurred (required datetime).
        type: Punch classification ('in', 'out', 'break_start', 'break_end').
        source: System or channel where the punch originated ('kiosk', 'mobile', 'web').
        device_id: Optional identifier of the device or hardware capturing the punch.
    """
    # Explicit table name matching foreign key conventions
    __tablename__ = "punch"

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the punch event",
    )

    # Required foreign key referencing employee.id
    employee_id: int = Field(
        foreign_key="employee.id",
        nullable=False,
        index=True,
        description="Foreign key referencing employee.id",
    )

    # Required punch timestamp (supports both naive and UTC timezone datetimes)
    ts: datetime = Field(
        sa_type=DateTime,
        nullable=False,
        index=True,
        description="Timestamp when the punch was recorded (required)",
    )

    # Required punch event type strictly validated against PunchType enum
    type: PunchType = Field(
        nullable=False,
        index=True,
        description="Punch event type ('in', 'out', 'break_start', 'break_end')",
    )

    # Required punch origin source strictly validated against PunchSource enum
    source: PunchSource = Field(
        nullable=False,
        index=True,
        description="Source of the punch ('kiosk', 'mobile', 'web')",
    )

    # Optional hardware/device identifier (e.g. tablet ID, kiosk MAC, mobile device UUID)
    device_id: Optional[str] = Field(
        default=None,
        nullable=True,
        max_length=255,
        description="Optional identifier of the device or hardware capturing the punch",
    )

    # --------------------------------------------------------------------------
    # Constructor Validation for Enum Safety
    # --------------------------------------------------------------------------
    def __init__(self, **data):
        """
        Validates enum values during direct object construction.
        """
        super().__init__(**data)
        if hasattr(self, "type") and self.type is not None:
            if isinstance(self.type, str):
                try:
                    self.type = PunchType(self.type)
                except ValueError:
                    allowed = [e.value for e in PunchType]
                    raise ValueError(f"Invalid punch type '{self.type}'. Allowed values: {allowed}")
        if hasattr(self, "source") and self.source is not None:
            if isinstance(self.source, str):
                try:
                    self.source = PunchSource(self.source)
                except ValueError:
                    allowed = [e.value for e in PunchSource]
                    raise ValueError(f"Invalid punch source '{self.source}'. Allowed values: {allowed}")

    # --------------------------------------------------------------------------
    # Future Relationships (to be activated when full relationship graph is wired)
    # --------------------------------------------------------------------------
    # employee: Optional["Employee"] = Relationship(back_populates="punches")
