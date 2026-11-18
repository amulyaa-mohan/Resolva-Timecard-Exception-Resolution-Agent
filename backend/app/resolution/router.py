"""Decision and audit APIs (A-03). Identity comes only from the bearer credential."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.attendance.access import ManagerCredential, authenticated_manager
from app.attendance.repository import CaseAccessDenied
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
