import pytest

from app.ai.pipeline import generate_proposal
from app.ai.providers import build_provider
from app.attendance.context import CaseService, build_verified_case
from app.attendance.repository import CaseAccessDenied, DemoCaseRepository
from app.core.contracts import GateStatus
from app.rules.validator import validate_correction
from tests.factories import make_case


def test_persistence_restart_and_manager_scope(tmp_path):
    path = tmp_path / "demo.sqlite"
    repo = DemoCaseRepository(path)
    case = make_case()
    repo.seed_case(case, manager_id="manager-1")
    repo.seed_case(case, manager_id="manager-1")
    service = CaseService(DemoCaseRepository(path))
    assert service.build_case_context("X-1", manager_id="manager-1").employee == case.employee
    for identity, exception in [("manager-2", "X-1"), ("manager-1", "unknown")]:
        with pytest.raises(CaseAccessDenied):
            service.build_case_context(exception, manager_id=identity)


def test_seed_never_overwrites(tmp_path):
    repo = DemoCaseRepository(tmp_path / "demo.sqlite")
    repo.seed_case(make_case(), manager_id="manager-1")
    with pytest.raises(ValueError, match="reassign"):
        repo.seed_case(make_case(), manager_id="manager-2")
    with pytest.raises(ValueError, match="overwrite"):
        repo.seed_case(make_case(notes=("Changed",)), manager_id="manager-1")


def test_evidence_changes_with_notes_and_revision():
    original = build_verified_case(make_case(), correction_revision=0)
    assert (
        original.evidence_version
        == build_verified_case(make_case(), correction_revision=0).evidence_version
    )
    assert (
        original.evidence_version
        != build_verified_case(make_case(), correction_revision=1).evidence_version
    )
    assert (
        original.evidence_version
        != build_verified_case(
            make_case(notes=("changed",)), correction_revision=0
        ).evidence_version
    )


def test_cross_employee_rejected():
    case = make_case()
    data = case.model_dump()
    data["punches"][0]["employee_id"] = "other"
    with pytest.raises(ValueError, match="cross-employee"):
        build_verified_case(type(case).model_validate(data), correction_revision=0)


def test_real_track_a_validator_blocks_mock_until_complete(policy, settings):
    case = build_verified_case(make_case(), correction_revision=0)
    result = generate_proposal(
        case,
        policy,
        provider=build_provider(settings),
        validator=validate_correction,
        settings=settings,
    )
    assert result.status == GateStatus.BLOCKED
    assert result.validation is not None and not result.validation.passed
    assert any("incomplete" in check.reason for check in result.validation.checks)


def test_hash_is_stable_for_note_order_and_equivalent_offsets():
    from datetime import UTC

    original = make_case(notes=("first", "second"))
    data = original.model_dump()
    data["notes"].reverse()
    data["punches"][0]["ts"] = data["punches"][0]["ts"].astimezone(UTC)
    rebuilt = type(original).model_validate(data)
    assert (
        build_verified_case(original, correction_revision=0).evidence_version
        == build_verified_case(rebuilt, correction_revision=0).evidence_version
    )


def test_case_identity_and_local_work_date_checked():
    from datetime import timedelta

    original = make_case()
    data = original.model_dump()
    data["work_date"] += timedelta(days=1)
    with pytest.raises(ValueError, match="shift-start"):
        build_verified_case(type(original).model_validate(data), correction_revision=0)
    data = original.model_dump()
    data["punch_history"] = data["punches"]
    with pytest.raises(ValueError, match="duplicate punch"):
        build_verified_case(type(original).model_validate(data), correction_revision=0)


def test_loaded_case_mutation_does_not_modify_persisted_evidence(tmp_path):
    repo = DemoCaseRepository(tmp_path / "demo.sqlite")
    repo.seed_case(make_case(), manager_id="manager-1")
    service = CaseService(repo)
    first = service.build_case_context("X-1", manager_id="manager-1")
    expected = first.evidence_version
    first.punches.clear()  # Draft contract containers are only shallowly frozen.
    second = service.build_case_context("X-1", manager_id="manager-1")
    assert len(second.punches) == 1
    assert second.evidence_version == expected
