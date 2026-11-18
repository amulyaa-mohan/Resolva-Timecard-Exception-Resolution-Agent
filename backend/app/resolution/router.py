"""Decision and audit APIs (A-03). Identity comes only from the bearer credential."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.ai.providers import ProviderError, build_provider
from app.attendance.access import ManagerCredential, authenticated_manager
from app.attendance.repository import CaseAccessDenied
from app.core.contracts import ProposalResult, PunchRecord
from app.core.errors import problem
from app.resolution.store import (
    DecisionConflict,
    DecisionRequest,
    DecisionResult,
    StaleEvidence,
    ValidationRejected,
)

router = APIRouter(prefix="/exceptions", tags=["resolution"])


class AuditEvent(BaseModel):
    event_id: str
    occurred_at: str
    actor_type: str
    actor_id: str
    event_type: str
    exception_id: str
    decision_id: str | None
    payload: dict
    prev_hash: str
    hash: str


@router.post(
    "/{exception_id}/decisions",
    response_model=DecisionResult,
    responses={
        404: {"description": "Unknown or not assigned to this manager"},
        409: {
            "description": "Stale evidence (errors[0].current_evidence_version), already resolved, or idempotency key reuse"
        },
        422: {"description": "Correction fails deterministic validation (audited)"},
    },
)
def decide(
    exception_id: str,
    body: DecisionRequest,
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
) -> DecisionResult:
    store = request.app.state.resolution_store
    # RFC 7807 bodies via the shared helper; structured data goes in `errors`.
    try:
        return store.decide(exception_id, manager.manager_id, body)
    except CaseAccessDenied as exc:
        raise HTTPException(404, "Exception not found.") from exc
    except StaleEvidence as exc:
        return problem(
            409,
            "Evidence changed since this proposal; re-propose on the latest evidence.",
            title="Stale evidence",
            errors=[{"type": "stale_evidence", "current_evidence_version": exc.current}],
        )
    except DecisionConflict as exc:
        return problem(409, str(exc), title="Decision conflict", errors=[{"type": "conflict"}])
    except ValidationRejected as exc:
        return problem(422, str(exc), title="Validation failed", errors=exc.checks)


class BulkItem(DecisionRequest):
    exception_id: str = Field(min_length=1, max_length=128)


class BulkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BulkItem] = Field(min_length=1, max_length=50)


class BulkItemResult(BaseModel):
    exception_id: str
    ok: bool
    status_code: int
    result: DecisionResult | None = None
    error: str | None = None
    checks: list[dict] | None = None


@router.post("/bulk-decisions", response_model=list[BulkItemResult])
def bulk_decide(
    body: BulkRequest,
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
) -> list[BulkItemResult]:
    """Each item is authorized, validated and committed on its own (A-06).

    One item failing never rolls back or blocks another; nothing is approved without
    passing every check. Results are returned in request order.
    """
    store = request.app.state.resolution_store
    if len({i.idempotency_key for i in body.items}) != len(body.items):
        raise HTTPException(422, "Each bulk item needs its own idempotency_key.")
    results = []
    for item in body.items:
        decision = DecisionRequest(**item.model_dump(exclude={"exception_id"}))
        try:
            result = store.decide(item.exception_id, manager.manager_id, decision)
            results.append(
                BulkItemResult(
                    exception_id=item.exception_id, ok=True, status_code=200, result=result
                )
            )
        except CaseAccessDenied:
            results.append(
                BulkItemResult(
                    exception_id=item.exception_id,
                    ok=False,
                    status_code=404,
                    error="Exception not found.",
                )
            )
        except StaleEvidence as exc:
            results.append(
                BulkItemResult(
                    exception_id=item.exception_id,
                    ok=False,
                    status_code=409,
                    error=f"stale_evidence; current {exc.current}",
                )
            )
        except DecisionConflict as exc:
            results.append(
                BulkItemResult(
                    exception_id=item.exception_id, ok=False, status_code=409, error=str(exc)
                )
            )
        except ValidationRejected as exc:
            results.append(
                BulkItemResult(
                    exception_id=item.exception_id,
                    ok=False,
                    status_code=422,
                    error=str(exc),
                    checks=exc.checks,
                )
            )
    return results


class EffectiveTimecard(BaseModel):
    exception_id: str
    employee_id: str
    work_date: date
    raw_punches: list[PunchRecord]
    corrections_applied: list[dict]
    effective_punches: list[PunchRecord]
    net_worked_hours: float | None = Field(
        description="Null when the effective punches still cannot be paired."
    )


@router.post(
    "/{exception_id}/proposal",
    response_model=ProposalResult,
    responses={
        404: {"description": "Unknown or not assigned to this manager"},
        409: {"description": "Already resolved"},
    },
)
def propose(
    exception_id: str,
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
) -> ProposalResult:
    """Draft a correction with Track B's pipeline and store it with its model trace.

    Returns eligible / blocked / escalated. It never approves anything: approving is a
    separate, authorized decision that re-validates against fresh evidence.
    """
    store = request.app.state.resolution_store
    settings = request.app.state.settings
    try:
        provider = build_provider(settings)
    except ProviderError as exc:
        return problem(503, str(exc), title="Model provider unavailable")
    try:
        return store.propose(exception_id, manager.manager_id, provider=provider, settings=settings)
    except CaseAccessDenied as exc:
        raise HTTPException(404, "Exception not found.") from exc
    except DecisionConflict as exc:
        return problem(409, str(exc), title="Decision conflict", errors=[{"type": "conflict"}])


@router.get("/{exception_id}/timecard", response_model=EffectiveTimecard)
def timecard(
    exception_id: str,
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
):
    """Raw punches, the approved corrections applied to them, and the resulting hours."""
    try:
        return request.app.state.resolution_store.effective_timecard(
            exception_id, manager.manager_id
        )
    except CaseAccessDenied as exc:
        raise HTTPException(404, "Exception not found.") from exc


@router.get("/{exception_id}/audit", response_model=list[AuditEvent])
def audit_trail(
    exception_id: str,
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
) -> list[dict]:
    try:
        return request.app.state.resolution_store.audit_trail(exception_id, manager.manager_id)
    except CaseAccessDenied as exc:
        raise HTTPException(404, "Exception not found.") from exc
