"""
Location Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `Location` SQLModel database table, representing physical
or regional workplaces (offices, branches, stores) tied to an organization, each
with its own regional timezone and location rules.
"""

from typing import TYPE_CHECKING, List, Optional
from sqlmodel import Field, Relationship, SQLModel

# TYPE_CHECKING is True only during static type analysis (mypy, IDE autocomplete).
# It prevents circular imports and runtime mapper errors while dependent models
# and relationships are being incrementally built.
if TYPE_CHECKING:
    from .employee import Employee
    from .organization import Organization


# ------------------------------------------------------------------------------
# Location Database Model
# ------------------------------------------------------------------------------
class Location(SQLModel, table=True):
    """
    Represents a workplace location in the database.

    Attributes:
        id: Unique identifier for the location (auto-generated primary key).
        organization_id: Foreign key referencing the parent organization ('organization.id').
        name: Name or description of the location (required string).
        city: City where the location is situated (required string).
        country: Country where the location is situated (required string).
        timezone: Regional timezone string (e.g., 'America/New_York', 'UTC').
    """
    # Explicit table name as specified in requirements
    __tablename__ = "location"

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the location",
    )

    # Required foreign key referencing organization.id; indexed for join performance
    organization_id: int = Field(
        foreign_key="organization.id",
        nullable=False,
        index=True,
        description="Foreign key referencing organization.id",
    )

    # Required location name, indexed for fast lookups
    name: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=255,
        description="Name of the location (required)",
    )

    # Required city name, indexed for filtering by city
    city: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=255,
        description="City where the location is situated (required)",
    )

    # Required country name, indexed for filtering by country/jurisdiction
    country: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=255,
        description="Country where the location is situated (required)",
    )

    # Required timezone string for accurate timecard shift parsing
    timezone: str = Field(
        nullable=False,
        min_length=1,
        max_length=100,
        description="Timezone of the location (e.g., 'America/New_York', 'UTC')",
    )

    # --------------------------------------------------------------------------
    # Future Relationships (to be activated when full relationship graph is wired)
    # --------------------------------------------------------------------------
    # organization: Optional["Organization"] = Relationship(back_populates="locations")
    # employees: List["Employee"] = Relationship(back_populates="location")
