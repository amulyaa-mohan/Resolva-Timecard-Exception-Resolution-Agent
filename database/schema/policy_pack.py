"""
Policy Pack Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `PolicyPack` SQLModel database table, representing standardized
bundles of compliance rules, break requirements, overtime thresholds, and timecard
exception parameters applicable to specific jurisdictions (e.g., 'IN-KA', 'US-FED').
"""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

# TYPE_CHECKING is True only during static type analysis (mypy, IDE autocomplete).
# It prevents circular imports while dependent models are loaded.
if TYPE_CHECKING:
    from .employee import Employee


# ------------------------------------------------------------------------------
# PolicyPack Database Model
# ------------------------------------------------------------------------------
class PolicyPack(SQLModel, table=True):
    """
    Represents a policy pack containing overtime and compliance rules.

    Attributes:
        id: Unique identifier for the policy pack (auto-generated primary key).
        code: Identifier code for the policy pack (e.g., 'IN-KA', 'US-FED').
        name: Human-readable name of the policy pack (required string).
        version: Release or version string (e.g., '1.0', '2026.1').
        jurisdiction: Regional, state, or federal jurisdiction covered by this policy.
        is_active: Whether this policy pack is currently active (defaults to True).
    """
    # Explicit table name matching foreign key references in other models (e.g., 'policy_packs.id')
    __tablename__ = "policy_packs"

    # Enforce uniqueness for the combination of policy pack code and version
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_policy_packs_code_version"),
    )

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the policy pack",
    )

    # Required policy pack code (e.g., 'IN-KA', 'US-FED'), indexed for fast lookups
    code: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=50,
        description="Policy pack code (e.g., 'IN-KA', 'US-FED')",
    )

    # Required descriptive name of the policy pack
    name: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=255,
        description="Descriptive name of the policy pack",
    )

    # Required version string (e.g., '1.0', '2026.1')
    version: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=50,
        description="Version string for the policy pack (e.g., '1.0', '2026.1')",
    )

    # Required jurisdiction (e.g., 'India - Karnataka', 'US Federal')
    jurisdiction: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=100,
        description="Jurisdiction covered by the policy pack (e.g., 'India - Karnataka', 'US Federal')",
    )

    # Active status flag, defaults to True
    is_active: bool = Field(
        default=True,
        nullable=False,
        description="Whether the policy pack is active (defaults to True)",
    )

    # --------------------------------------------------------------------------
    # Future Relationships (to be activated when full relationship graph is wired)
    # --------------------------------------------------------------------------
    # employees: List["Employee"] = Relationship(back_populates="policy_pack")
