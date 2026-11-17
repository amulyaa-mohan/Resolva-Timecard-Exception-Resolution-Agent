"""RFC 7807 problem+json error responses."""

from __future__ import annotations

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.tracing import TRACE_HEADER, get_trace_id

PROBLEM_JSON = "application/problem+json"


def problem(
    status: int, detail: str, *, title: str | None = None, errors: list | None = None
) -> JSONResponse:
    trace_id = get_trace_id()
    body: dict = {
        "type": "about:blank",
        "title": title or HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "trace_id": trace_id,
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(
        body, status_code=status, media_type=PROBLEM_JSON, headers={TRACE_HEADER: trace_id}
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return problem(422, "Request validation failed.", errors=errors)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return problem(500, "Internal server error.")
