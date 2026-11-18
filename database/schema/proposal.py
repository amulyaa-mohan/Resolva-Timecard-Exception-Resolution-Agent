"""
Proposal Model for Resolva – Timecard Exception Resolution Agent.

This module defines the `Proposal` SQLModel database table, representing resolution
actions proposed by the AI agent or rule engine for a detected timecard exception.
Each proposal captures actionable steps, rationale, citations, confidence scores,
and guardrail validation outputs.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional
from pydantic import model_validator
from sqlalchemy import CheckConstraint, Column, JSON
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .exception import ExceptionRecord


# ------------------------------------------------------------------------------
# Proposal Database Model
# ------------------------------------------------------------------------------
class Proposal(SQLModel, table=True):
    """
    Represents an AI-generated or engine-generated resolution proposal for a timecard exception.

    Attributes:
        id: Unique identifier for the proposal (auto-generated primary key).
        exception_id: Foreign key referencing the associated exception record ('exception_record.id').
        actions: Required JSON-compatible list of proposed actions (e.g. insert punch, adjust shift).
        rationale: Required textual explanation detailing the reasoning behind the proposed actions.
        citations: JSON-compatible list of policy citations or legal references (defaults to []).
        confidence: Required confidence score between 0.0 and 1.0 representing model certainty.
        model_id: Optional string identifying the LLM or engine model that generated the proposal.
        prompt_hash: Optional string hash of the prompt template / system prompt version used.
        validator_result: Optional structured JSON data containing guardrail validation results.
        gate_decision: Optional string outcome of the automated approval gate (e.g., 'auto_apply', 'manual_review').
    """
    # Explicit table name matching SQL conventions
    __tablename__ = "proposal"

    # Database-level check constraints for SQLite and SQL engines
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="check_proposal_confidence_range",
        ),
    )

    # Primary Key: automatically generated integer ID
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        index=True,
        description="Unique identifier for the proposal",
    )

    # Required foreign key referencing exception_record.id
    exception_id: int = Field(
        foreign_key="exception_record.id",
        nullable=False,
        index=True,
        description="Foreign key referencing exception_record.id",
    )

    # Required JSON-compatible list of proposed actions
    actions: List[Any] = Field(
        sa_column=Column(JSON, nullable=False),
        description="Required JSON-compatible list of proposed actions",
    )

    # Required explanation and reasoning
    rationale: str = Field(
        nullable=False,
        min_length=1,
        description="Textual rationale and reasoning supporting the proposal",
    )

    # JSON-compatible list of policy citations, defaults to empty list
    citations: List[Any] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
        description="JSON-compatible list of policy or rule citations (defaults to empty list)",
    )

    # Required confidence score between 0.0 and 1.0
    confidence: float = Field(
        nullable=False,
        ge=0.0,
        le=1.0,
        index=True,
        description="Confidence score between 0.0 and 1.0",
    )

    # Optional string identifying the model
    model_id: Optional[str] = Field(
        default=None,
        nullable=True,
        max_length=100,
        description="Identifier of the model generating the proposal (optional)",
    )

    # Optional hash of prompt
    prompt_hash: Optional[str] = Field(
        default=None,
        nullable=True,
        max_length=128,
        description="Hash of the prompt template and inputs used (optional)",
    )

    # Optional JSON-compatible data for validator results
    validator_result: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Structured JSON output from deterministic validation and guardrails",
    )

    # Optional decision outcome from automated policy gate
    gate_decision: Optional[str] = Field(
        default=None,
        nullable=True,
        max_length=50,
        description="Gate decision outcome ('auto_apply', 'manual_review', 'rejected', etc.)",
    )

    # --------------------------------------------------------------------------
    # Pydantic & Constructor Validation
    # --------------------------------------------------------------------------
    @model_validator(mode="after")
    def validate_proposal_fields(self):
        """
        Validates confidence range and structured list types.
        """
        if self.confidence is not None:
            if not (0.0 <= float(self.confidence) <= 1.0):
                raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        if self.actions is not None and not isinstance(self.actions, list):
            raise ValueError("actions must be a list of proposed actions")
        if self.citations is not None and not isinstance(self.citations, list):
            raise ValueError("citations must be a list")
        return self

    def __init__(self, **data):
        """
        Constructor validation to ensure constraints are enforced during direct instantiation.
        """
        super().__init__(**data)
        if hasattr(self, "confidence") and self.confidence is not None:
            if not (0.0 <= float(self.confidence) <= 1.0):
                raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        if hasattr(self, "actions") and self.actions is not None:
            if not isinstance(self.actions, list):
                raise ValueError("actions must be a list of proposed actions")
        if hasattr(self, "citations") and self.citations is not None:
            if not isinstance(self.citations, list):
                raise ValueError("citations must be a list")

    # --------------------------------------------------------------------------
    # Future Relationships (to be activated when full relationship graph is wired)
    # --------------------------------------------------------------------------
    # exception_record: Optional["ExceptionRecord"] = Relationship(back_populates="proposals")
