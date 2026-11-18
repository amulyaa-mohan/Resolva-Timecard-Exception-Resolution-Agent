"""
Organization Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `Organization` SQLModel database table, representing the top-level
company, business entity, or tenant managing timecard policies, locations, and employees.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel


def get_utc_now() -> datetime:
    """
    Returns the current date and time in UTC.
    Used as the default_factory for timestamp fields.
    """
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------
# Organization Database Model
# ------------------------------------------------------------------------------
class Organization(SQLModel, table=True):
    """
    Represents an organization or company entity in the database.

    Attributes:
        id: Unique identifier for the organization (auto-generated primary key).
        name: Name of the organization (required string).
        code: Unique business code or identifier for the organization (required string).
        created_at: Timestamp when the organization record was created (UTC).
    """
    # Table name matching foreign key references (e.g., 'organization.id')
    __tablename__ = "organization"

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the organization",
    )

    # Required organization name with length validation and indexing for fast lookups
    name: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=255,
        description="Name of the organization (required)",
    )

    # Required unique organization code (e.g., 'CORP-01', 'ACME')
    code: str = Field(
        nullable=False,
        unique=True,
        index=True,
        min_length=1,
        max_length=50,
        description="Unique business code for the organization (required)",
    )

    # Creation timestamp defaulting to current UTC time
    created_at: datetime = Field(
        default_factory=get_utc_now,
        nullable=False,
        description="Timestamp when the organization was created (defaults to UTC now)",
    )
