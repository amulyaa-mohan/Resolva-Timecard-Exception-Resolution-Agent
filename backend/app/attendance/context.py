"""Track A boundary around the shared draft; no HTTP or database coupling."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from app.core.contracts import DEFAULT_SEVERITY, CaseContext


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def build_verified_case(case: CaseContext, *, correction_revision: int) -> CaseContext:
    """Validate repository evidence and derive a reproducible version token.

    Repository must increment correction_revision for every appended correction.
    Policy/prompt versions remain separate proposal eligibility checks.
    """
    if correction_revision < 0:
        raise ValueError("invalid correction revision")
    # Revalidate because frozen Pydantic containers are not deeply immutable.
    case = CaseContext.model_validate(case.model_dump())
    zone = ZoneInfo(case.employee.timezone)
    if case.severity != DEFAULT_SEVERITY[case.code]:
        raise ValueError("exception severity does not match rule")
    if case.schedule:
        if case.schedule.employee_id != case.employee.employee_id:
            raise ValueError("schedule belongs to another employee")
        if case.schedule.start.astimezone(zone).date() != case.work_date:
            raise ValueError("work_date must be local shift-start date")
    punches = case.punches + case.punch_history
    if any(p.employee_id != case.employee.employee_id for p in punches):
        raise ValueError("cross-employee evidence")
    if len({p.punch_id for p in punches}) != len(punches):
        raise ValueError("duplicate punch identity")
    if len({n.note_id for n in case.notes}) != len(case.notes):
        raise ValueError("duplicate note identity")
    # as_of is evaluation time, not evidence: reloading must not make approvals stale.
    payload = case.model_dump(exclude={"evidence_version", "as_of"})
    for field, key in [
        ("punches", "punch_id"),
        ("punch_history", "punch_id"),
        ("notes", "note_id"),
    ]:
        payload[field] = sorted(payload[field], key=lambda item: item[key])
    payload["correction_revision"] = correction_revision
    encoded = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
    ).encode()
    return case.model_copy(
        update={"evidence_version": "sha256:" + hashlib.sha256(encoded).hexdigest()}
    )


class CaseRepository(Protocol):
    def load_for_manager(self, exception_id: str, manager_id: str) -> tuple[CaseContext, int]:
        """Load authorized evidence and correction revision in one consistent read."""
        ...


class CaseService:
    """Trusted application boundary. manager_id must come from authenticated identity."""

    def __init__(
        self, repository: CaseRepository, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ):
        self.repository = repository
        self.clock = clock

    def build_case_context(self, exception_id: str, *, manager_id: str) -> CaseContext:
        case, revision = self.repository.load_for_manager(exception_id, manager_id)
        case = build_verified_case(case, correction_revision=revision)
        # Server clock, never the client's (contract 0.2.0).
        return case.model_copy(update={"as_of": self.clock().astimezone(UTC)})
