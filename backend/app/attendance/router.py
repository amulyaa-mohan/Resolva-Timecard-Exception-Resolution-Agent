"""Read-only attendance APIs using server identity and persistent employee assignments."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.attendance.access import ManagerCredential, authenticated_manager
from app.attendance.context import CaseService
from app.attendance.queries import ExceptionFilter
from app.attendance.repository import CaseAccessDenied
from app.core.contracts import CaseContext, ExceptionCode, Severity
from app.language.assistant import resolve_dates
from app.language.intents import DateRange

router = APIRouter(prefix="/exceptions", tags=["attendance"])


class ExceptionSummary(BaseModel):
    exception_id: str
    employee_id: str
    employee_name: str | None = Field(
        default=None, description="Display only; null when the store keeps no personal data."
    )
    code: ExceptionCode
    severity: Severity
    work_date: date
    status: Literal["open", "escalated", "resolved"] = "open"
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
    status: Literal["open", "escalated", "resolved"] | None = None,
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
    repository = request.app.state.attendance_repository
    page, total = repository.search_exceptions(
        manager.manager_id,
        ExceptionFilter(
            code=exception_type,
            severity=severity,
            status=status,
            employee_id=employee_id,
            exception_id=exception_id,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
        ),
    )
    names = repository.display_names(sorted({c.employee.employee_id for c, _ in page}))
    return ExceptionPage(
        items=[
            ExceptionSummary(
                exception_id=c.exception_id,
                employee_id=c.employee.employee_id,
                employee_name=names.get(c.employee.employee_id),
                code=c.code,
                severity=c.severity,
                work_date=c.work_date,
                status=case_status,
                evidence_version=c.evidence_version,
            )
            for c, case_status in page
        ],
        total=total,
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
