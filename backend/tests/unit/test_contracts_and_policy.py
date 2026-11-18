from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.core.contracts import (
    ALLOWED_ACTIONS,
    DEFAULT_SEVERITY,
    EmployeeContext,
    ExceptionCode,
    LLMProposal,
    ProposedAction,
)
from app.policies.registry import PolicyRegistry, PolicyResolutionError, chunk_handbook


def test_every_exception_code_has_actions_and_severity():
    assert set(ALLOWED_ACTIONS) == set(ExceptionCode)
    assert set(DEFAULT_SEVERITY) == set(ExceptionCode)


def test_escalation_needs_no_citations_or_actions():
    p = LLMProposal(exception_id="X", decision="escalate", rationale="no schedule", confidence=0.0)
    assert p.citations == [] and p.actions == []


def test_escalation_cannot_carry_actions():
    with pytest.raises(ValidationError):
        LLMProposal(
            exception_id="X",
            decision="escalate",
            actions=[{"type": "acknowledge"}],
            rationale="r",
            confidence=0.1,
        )


def test_proposal_requires_citation():
    with pytest.raises(ValidationError):
        LLMProposal(
            exception_id="X",
            decision="propose",
            actions=[{"type": "acknowledge"}],
            rationale="r",
            confidence=0.9,
        )


def test_naive_timestamps_rejected():
    with pytest.raises(ValidationError):
        ProposedAction(type="add_punch", punch_type="out", new_ts=datetime(2026, 11, 12, 18))


def test_add_punch_requires_time_and_type():
    with pytest.raises(ValidationError):
        ProposedAction(type="add_punch")


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        LLMProposal(
            exception_id="X", decision="escalate", rationale="r", confidence=0, apply_now=True
        )


def test_in_ka_pack_loads_with_versioned_chunk_ids(policy):
    assert policy.rules.daily_regular_hours == 9
    assert policy.rules.max_spread_hours == 12
    ids = [c.chunk_id for c in policy.clauses]
    assert "IN-KA@2025.1#KA-8" in ids
    assert all(i.startswith("IN-KA@2025.1#") for i in ids)
    assert len(policy.content_hash) == 64


def test_resolve_by_jurisdiction_and_date(registry):
    emp = EmployeeContext(
        employee_id="E", location_id="L", jurisdiction="IN-KA", timezone="Asia/Kolkata"
    )
    assert registry.resolve(emp, date(2026, 11, 12)).version == "2025.1"
    with pytest.raises(PolicyResolutionError):
        registry.resolve(emp, date(2024, 12, 31))  # before effective_from
    other = emp.model_copy(update={"jurisdiction": "US-TX"})  # no such pack
    with pytest.raises(PolicyResolutionError):
        registry.resolve(other, date(2026, 11, 12))


def test_ambiguous_active_versions_refuse_to_guess(policy):
    clone = policy.model_copy(update={"version": "2025.9"})
    emp = EmployeeContext(
        employee_id="E", location_id="L", jurisdiction="IN-KA", timezone="Asia/Kolkata"
    )
    with pytest.raises(PolicyResolutionError, match="ambiguous"):
        PolicyRegistry([policy, clone]).resolve(emp, date(2026, 11, 12))


def test_chunker_rejects_duplicate_clause_ids():
    md = "## [A-1] One\ntext\n## [A-1] Again\nmore"
    with pytest.raises(ValueError):
        chunk_handbook(md, "P", "1")
