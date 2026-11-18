"""Import APIs (A-05). PostgreSQL only; rows are limited to the manager's assigned employees."""

from datetime import UTC
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.attendance.access import ManagerCredential, authenticated_manager
from app.attendance.importer import (
    PUNCH_FIELDS,
    SHIFT_FIELDS,
    ImportFileError,
    ImportPreview,
    local_dates,
    preview_punches,
    preview_shifts,
    read_rows,
)
from app.core.errors import problem

router = APIRouter(prefix="/imports", tags=["imports"])


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["punches", "shifts"] = "punches"
    format: Literal["csv", "json"]
    content: str = Field(min_length=1)
    mapping: dict[str, str] = Field(
        default_factory=dict, description="Canonical field -> column name in the file."
    )
    allow_partial: bool = Field(
        default=False, description="Commit valid rows even when some rows are invalid."
    )


class ImportResult(BaseModel):
    batch_id: str
    inserted: int
    invalid: int
    duplicates: int
    detected_exception_ids: list[str]


def _postgres(request: Request):
    from app.attendance.postgres import PostgresCaseRepository

    repository = request.app.state.attendance_repository
    if not isinstance(repository, PostgresCaseRepository):
        raise HTTPException(501, "Imports need the PostgreSQL store (ATTENDANCE_DATABASE_URL).")
    return repository.backend


def _preview(request: Request, body: ImportRequest, manager_id: str):
    from app.attendance.ingest import assigned_employees, existing_keys

    backend = _postgres(request)
    allowed = set(PUNCH_FIELDS if body.kind == "punches" else SHIFT_FIELDS)
    unknown = sorted(set(body.mapping) - allowed)
    if unknown:
        raise HTTPException(422, f"Unknown mapping fields: {', '.join(unknown)}")
    rows = read_rows(body.content, body.format)
    employees = assigned_employees(backend, manager_id)
    if body.kind == "shifts":
        return (
            backend,
            employees,
            preview_shifts(rows, employee_timezones=employees, mapping=body.mapping),
        )
    first = preview_punches(rows, employee_timezones=employees, mapping=body.mapping)
    known = existing_keys(backend, first)
    if not known:
        return backend, employees, first
    return (
        backend,
        employees,
        preview_punches(
            rows, employee_timezones=employees, mapping=body.mapping, existing_keys=known
        ),
    )


@router.post("/preview", response_model=ImportPreview)
def preview_import(
    body: ImportRequest,
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
):
    try:
        return _preview(request, body, manager.manager_id)[2]
    except ImportFileError as exc:
        return problem(422, str(exc), title="Unreadable import file")


@router.post("", response_model=ImportResult)
def commit(
    body: ImportRequest,
    request: Request,
    manager: Annotated[ManagerCredential, Depends(authenticated_manager)],
):
    from app.attendance.ingest import commit_import, new_batch_id, run_detection

    try:
        backend, employees, preview = _preview(request, body, manager.manager_id)
    except ImportFileError as exc:
        return problem(422, str(exc), title="Unreadable import file")
    if preview.invalid and not body.allow_partial:
        return problem(
            422,
            f"{preview.invalid} invalid row(s); fix them or set allow_partial.",
            title="Import has invalid rows",
            errors=[r.model_dump(mode="json") for r in preview.rows if r.status == "invalid"],
        )
    batch_id = new_batch_id()
    inserted = commit_import(backend, preview, batch_id=batch_id)
    detected = run_detection(
        backend,
        request.app.state.resolution_store.registry,
        local_dates(preview, employees),
        as_of=request.app.state.resolution_store.clock().astimezone(UTC),
    )
    return ImportResult(
        batch_id=batch_id,
        inserted=inserted,
        invalid=preview.invalid,
        duplicates=preview.duplicates,
        detected_exception_ids=detected,
    )
