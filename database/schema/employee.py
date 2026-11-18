"""
Employee Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `Employee` SQLModel database table, representing workers
whose timecards, shifts, compensation types, and policy compliance are managed by Resolva.
"""

from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from sqlmodel import Field, Relationship, SQLModel

# TYPE_CHECKING prevents circular import issues during static type analysis
if TYPE_CHECKING:
    from .location import Location
    from .policy_pack import PolicyPack


# ------------------------------------------------------------------------------
# 1. Pay Type Enumeration
# ------------------------------------------------------------------------------
class PayType(str, Enum):
    """
    Allowed compensation types for an employee.

    - HOURLY: Compensated based on tracked working hours.
    - SALARIED: Fixed compensation regardless of recorded hours.
    """
    HOURLY = "hourly"
    SALARIED = "salaried"


# ------------------------------------------------------------------------------
# 2. Employee Database Model
# ------------------------------------------------------------------------------
class Employee(SQLModel, table=True):
    """
    Represents an employee record in the database.

    Attributes:
        id: Unique identifier for the employee (auto-generated primary key).
        name: Full name of the employee (required string).
        location_id: Foreign key referencing 'location.id' (required integer).
        job: Job title or role description (required string).
        pay_type: Compensation classification ('hourly' or 'salaried' via PayType enum).
        policy_pack_id: Foreign key referencing 'policy_packs.id' (required integer).
        manager_id: Self-referencing foreign key referencing 'employee.id' (optional integer).
        manager: Self-referencing relationship pointing to this employee's manager.
        direct_reports: Self-referencing relationship pointing to reporting employees.
    """
    # Explicit table name matching foreign key references (e.g., 'employee.id')
    __tablename__ = "employee"

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the employee",
    )

    # Required employee name, indexed for fast lookups
    name: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=255,
        description="Full name of the employee (required)",
    )

    # Required foreign key referencing location.id based on Location model definition
    location_id: int = Field(
        foreign_key="location.id",
        nullable=False,
        index=True,
        description="Foreign key referencing location.id",
    )

    # Required job title or role
    job: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=255,
        description="Job title or role of the employee (required)",
    )

    # Required compensation type strictly using the PayType enum
    pay_type: PayType = Field(
        nullable=False,
        index=True,
        description="Employee pay type: strictly 'hourly' or 'salaried'",
    )

    # Required foreign key referencing policy_packs.id based on PolicyPack model definition
    policy_pack_id: int = Field(
        foreign_key="policy_packs.id",
        nullable=False,
        index=True,
        description="Foreign key referencing policy_packs.id",
    )

    # Optional self-referencing foreign key referencing employee.id (can be NULL)
    manager_id: Optional[int] = Field(
        default=None,
        foreign_key="employee.id",
        nullable=True,
        index=True,
        description="Optional self-referencing foreign key pointing to manager's employee.id",
    )

    # --------------------------------------------------------------------------
    # Relationships
    # --------------------------------------------------------------------------
    # Self-referencing relationship: An employee can have one manager
    manager: Optional["Employee"] = Relationship(
        back_populates="direct_reports",
        sa_relationship_kwargs={"remote_side": "Employee.id"},
    )

    # Self-referencing relationship: A manager can have multiple direct reports
    direct_reports: List["Employee"] = Relationship(
        back_populates="manager",
    )
