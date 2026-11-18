"""
Exception Record Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `ExceptionRecord` SQLModel database table, representing detected
timecard exceptions, compliance anomalies, rule deviations (e.g., missed punches,
unauthorized overtime, meal break violations), and their resolution status.
"""

from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .employee import Employee


# ------------------------------------------------------------------------------
# 1. Enums for Severity and Status
# ------------------------------------------------------------------------------
class ExceptionSeverity(str, Enum):
    """
    Severity classifications for timecard exceptions.

    - LOW: Informational deviation not impacting payroll calculation.
    - MEDIUM: Moderate deviation requiring supervisor or employee acknowledgement.
    - HIGH: Substantial deviation or unapproved overtime.
    - CRITICAL: Blocking payroll violation or wage-and-hour compliance breach.
    - INFO: Alias for informational/low priority flags.
    - WARNING: Alias for moderate warning flags.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    INFO = "info"
    WARNING = "warning"


class ExceptionStatus(str, Enum):
    """
    Lifecycle status of an exception resolution workflow.

    - OPEN: Newly detected exception awaiting review or agent action.
    - PENDING: Action drafted or waiting for manager/employee confirmation.
    - RESOLVED: Discrepancy successfully corrected or approved.
    - DISMISSED: Reviewed and flagged as false positive or approved deviation.
    - ESCALATED: Escalated to human HR/payroll administrator.
    """
    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    ESCALATED = "escalated"


# ------------------------------------------------------------------------------
# 2. ExceptionRecord Database Model
# ------------------------------------------------------------------------------
class ExceptionRecord(SQLModel, table=True):
    """
    Represents a detected timecard exception record in the database.

    Attributes:
        id: Unique identifier for the exception (auto-generated primary key).
        code: Classification code of the exception (e.g., 'MISSED_PUNCH', 'MEAL_BREAK_VIOLATION').
        severity: Severity level ('low', 'medium', 'high', 'critical').
        employee_id: Foreign key referencing the affected employee ('employee.id').
        work_date: Calendar date of the work shift on which the exception occurred.
        rule_version: Version of the policy pack rule applied during detection.
        evidence: Structured JSON data containing the raw data, calculations, and punch comparisons.
        status: Current workflow status ('open', 'pending', 'resolved', 'dismissed', 'escalated').
    """
    # Explicit table name matching SQL conventions
    __tablename__ = "exception_record"

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the exception record",
    )

    # Required classification code (e.g., 'MISSED_PUNCH', 'MEAL_BREAK_VIOLATION')
    code: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=100,
        description="Exception classification code (required)",
    )

    # Required severity level
    severity: ExceptionSeverity = Field(
        nullable=False,
        index=True,
        description="Severity level of the exception ('low', 'medium', 'high', 'critical')",
    )

    # Required foreign key referencing employee.id
    employee_id: int = Field(
        foreign_key="employee.id",
        nullable=False,
        index=True,
        description="Foreign key referencing employee.id",
    )

    # Required calendar work date for the shift/exception
    work_date: date = Field(
        nullable=False,
        index=True,
        description="Date of the shift when the exception occurred (required)",
    )

    # Required version of the rule pack that generated this exception
    rule_version: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=50,
        description="Version string of the policy rule pack applied (required)",
    )

    # Required JSON-compatible structured data stored in a SQLite-compatible JSON column
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
        description="Structured JSON data detailing the punches, deviations, and calculations",
    )

    # Required workflow resolution status
    status: ExceptionStatus = Field(
        default=ExceptionStatus.OPEN,
        nullable=False,
        index=True,
        description="Resolution status ('open', 'pending', 'resolved', 'dismissed', 'escalated')",
    )

    # --------------------------------------------------------------------------
    # Constructor Validation for Enum Safety
    # --------------------------------------------------------------------------
    def __init__(self, **data):
        """
        Validates severity and status during direct object instantiation.
        """
        super().__init__(**data)
        if hasattr(self, "severity") and self.severity is not None:
            if isinstance(self.severity, str):
                try:
                    self.severity = ExceptionSeverity(self.severity)
                except ValueError:
                    allowed = [e.value for e in ExceptionSeverity]
                    raise ValueError(f"Invalid severity '{self.severity}'. Allowed values: {allowed}")
        if hasattr(self, "status") and self.status is not None:
            if isinstance(self.status, str):
                try:
                    self.status = ExceptionStatus(self.status)
                except ValueError:
                    allowed = [e.value for e in ExceptionStatus]
                    raise ValueError(f"Invalid status '{self.status}'. Allowed values: {allowed}")

    # --------------------------------------------------------------------------
    # Future Relationships (to be activated when full relationship graph is wired)
    # --------------------------------------------------------------------------
    # employee: Optional["Employee"] = Relationship(back_populates="exceptions")
