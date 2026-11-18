"""Read-only attendance APIs using server identity and persistent employee assignments."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.attendance.access import ManagerCredential, authenticated_manager
from app.attendance.context import CaseService
from app.attendance.repository import CaseAccessDenied
from app.core.contracts import CaseContext, ExceptionCode, Severity
from app.language.assistant import resolve_dates
from app.language.intents import DateRange

router = APIRouter(prefix="/exceptions", tags=["attendance"])


class ExceptionSummary(BaseModel):
    exception_id: str
    employee_id: str
    code: ExceptionCode
    severity: Severity
    work_date: date
    status: Literal["open"] = "open"
    evidence_version: str


class ExceptionPage(BaseModel):
    items: list[ExceptionSummary]
    total: int
    offset: int
    limit: int


@router.get("", response_model=ExceptionPage)
def list_exceptions(
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
    exception_type: ExceptionCode | None = None,
    severity: Severity | None = None,
    status: Literal["open", "escalated"] | None = None,
    employee_id: str | None = Query(None, min_length=1, max_length=128),
    exception_id: str | None = Query(None, min_length=1, max_length=128),
    date_range: DateRange | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> ExceptionPage:
    if date_range and (date_from or date_to):
        raise HTTPException(422, "Choose date_range or explicit date bounds.")
    if date_range:
        today = datetime.now(UTC).astimezone(ZoneInfo(manager.timezone)).date()
        date_from, date_to = resolve_dates(date_range, today)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must not follow date_to.")
    cases = request.app.state.attendance_repository.list_for_manager(manager.manager_id)
    # Demo snapshots are open: decisions/escalations are not persisted in this adapter.
    filtered = [
        c
        for c in cases
        if (status in (None, "open"))
        and (exception_type is None or c.code == exception_type)
        and (severity is None or c.severity == severity)
        and (employee_id is None or c.employee.employee_id == employee_id)
        and (exception_id is None or c.exception_id == exception_id)
        and (date_from is None or c.work_date >= date_from)
        and (date_to is None or c.work_date <= date_to)
    ]
    filtered.sort(key=lambda c: (c.severity != Severity.PROBLEM, c.work_date, c.exception_id))
    return ExceptionPage(
        items=[
            ExceptionSummary(
                exception_id=c.exception_id,
                employee_id=c.employee.employee_id,
                code=c.code,
                severity=c.severity,
                work_date=c.work_date,
                evidence_version=c.evidence_version,
            )
            for c in filtered[offset : offset + limit]
        ],
        total=len(filtered),
        offset=offset,
        limit=limit,
    )


@router.get("/{exception_id}", response_model=CaseContext)
def exception_detail(
    exception_id: str,
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
) -> CaseContext:
    service = CaseService(request.app.state.attendance_repository)
    try:
        return service.build_case_context(exception_id, manager_id=manager.manager_id)
    except CaseAccessDenied as exc:
        raise HTTPException(404, "Exception not found.") from exc
