"""
Policy Clause Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `PolicyClause` SQLModel database table, representing discrete,
version-pinned statutory or organizational policy rules (e.g. meal break requirements,
overtime rules, spreadover caps). These clauses are referenced by AI proposals as
verifiable citations during exception resolution.
"""

from typing import TYPE_CHECKING, Optional
from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .policy_pack import PolicyPack


# ------------------------------------------------------------------------------
# PolicyClause Database Model
# ------------------------------------------------------------------------------
class PolicyClause(SQLModel, table=True):
    """
    Represents an individual policy clause within a versioned policy pack.

    Attributes:
        id: Unique identifier for the policy clause (auto-generated primary key).
        policy_pack_id: Foreign key referencing the parent policy pack ('policy_packs.id').
        clause_id: Unique business/statutory clause identifier (e.g., 'IN-KA-REST-01', 'US-FLSA-OT-01').
        section: Optional section, sub-clause, or rule number (e.g., 'Section 7(a)', '§ 512').
        content: Required full legal or policy text explaining the compliance rule.
        source_doc: Optional title of the governing statute, regulation, or employee handbook.
    """
    # Explicit table name matching foreign key conventions
    __tablename__ = "policy_clause"

    # Enforce uniqueness for the combination of policy pack and clause identifier
    __table_args__ = (
        UniqueConstraint(
            "policy_pack_id", "clause_id", name="uq_policy_clause_pack_clause"
        ),
    )

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the policy clause",
    )

    # Required foreign key referencing policy_packs.id
    policy_pack_id: int = Field(
        foreign_key="policy_packs.id",
        nullable=False,
        index=True,
        description="Foreign key referencing policy_packs.id",
    )

    # Required unique clause identifier within the pack (e.g., 'IN-KA-REST-01')
    clause_id: str = Field(
        nullable=False,
        index=True,
        min_length=1,
        max_length=100,
        description="Unique clause identifier code within the policy pack",
    )

    # Optional section or clause reference (e.g., 'Section 7(1)', '29 CFR § 785.48')
    section: Optional[str] = Field(
        default=None,
        nullable=True,
        max_length=100,
        description="Statutory section or handbook rule reference",
    )

    # Required textual content of the clause
    content: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Full text and specifications of the policy clause",
    )

    # Optional source document or statute name
    source_doc: Optional[str] = Field(
        default=None,
        nullable=True,
        max_length=255,
        description="Title of governing statute or source policy document",
    )

    # --------------------------------------------------------------------------
    # Future Relationships (to be activated when full relationship graph is wired)
    # --------------------------------------------------------------------------
    # policy_pack: Optional["PolicyPack"] = Relationship(back_populates="clauses")
