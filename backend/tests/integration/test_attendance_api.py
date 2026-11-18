import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.attendance.access import AttendanceSettings
from app.attendance.repository import DemoCaseRepository
from app.main import create_app
from tests.factories import make_case


@pytest.fixture
def attendance_client(tmp_path, settings):
    database = tmp_path / "cases.sqlite"
    repo = DemoCaseRepository(database)
    repo.seed_case(make_case(), manager_id="M-1")
    other = make_case().model_dump()
    other["exception_id"] = "X-2"
    other["employee"]["employee_id"] = "E-002"
    other["punches"][0]["employee_id"] = "E-002"
    other["schedule"]["employee_id"] = "E-002"
    repo.seed_case(type(make_case()).model_validate(other), manager_id="M-2")
    credentials = tmp_path / "credentials.json"
    credentials.write_text(
        json.dumps(
            [
                {
                    "manager_id": manager,
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "expires_at": (datetime.now(UTC) + timedelta(hours=hours)).isoformat(),
                    "timezone": "Asia/Kolkata",
                }
                for manager, token, hours in [
                    ("M-1", "test-token-one", 1),
                    ("M-2", "test-token-two", 1),
                    ("M-1", "expired", -1),
                ]
            ]
        )
    )
    app = create_app(
        settings,
        attendance_settings=AttendanceSettings(
            _env_file=None, enabled=True, database_path=database, credentials_path=credentials
        ),
    )
    with TestClient(app) as client:
        yield client


def auth(token="test-token-one"):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "headers", [{}, auth("invalid"), auth("expired"), {"X-Role": "admin", "X-Manager-Id": "M-1"}]
)
def test_no_spoofing_or_expired_tokens(attendance_client, headers):
    result = attendance_client.get("/exceptions", headers=headers)
    assert result.status_code == 401
    assert result.headers["content-type"].startswith("application/problem+json")
    assert "trace_id" in result.json()


def test_assignment_scopes_list_and_detail(attendance_client):
    first = attendance_client.get("/exceptions", headers=auth()).json()
    assert first["total"] == 1 and first["items"][0]["exception_id"] == "X-1"
    assert "punches" not in first["items"][0]
    assert attendance_client.get("/exceptions/X-1", headers=auth()).status_code == 200
    forbidden = attendance_client.get("/exceptions/X-2", headers=auth())
    missing = attendance_client.get("/exceptions/missing", headers=auth())
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json()["detail"] == missing.json()["detail"]
    assert (
        attendance_client.get("/exceptions?employee_id=E-002", headers=auth()).json()["total"] == 0
    )
    assert (
        attendance_client.get("/exceptions", headers=auth("test-token-two")).json()["items"][0][
            "exception_id"
        ]
        == "X-2"
    )


@pytest.mark.parametrize(
    "query,expected",
    [
        ("exception_type=MISSING_PUNCH", 1),
        ("severity=warning", 0),
        ("status=escalated", 0),
        ("date_from=2026-11-12&date_to=2026-11-12", 1),
        ("date_to=2026-11-11", 0),
        ("exception_id=X-2", 0),
    ],
)
def test_filters(attendance_client, query, expected):
    assert attendance_client.get("/exceptions?" + query, headers=auth()).json()["total"] == expected


@pytest.mark.parametrize(
    "query",
    [
        "limit=101",
        "offset=-1",
        "status=approved",
        "severity=critical",
        "date_from=2026-12-01&date_to=2026-11-01",
        "date_range=TODAY&date_from=2026-11-01",
    ],
)
def test_invalid_filters(attendance_client, query):
    assert attendance_client.get("/exceptions?" + query, headers=auth()).status_code == 422


def test_pagination_and_version(attendance_client):
    page = attendance_client.get("/exceptions?offset=1&limit=1", headers=auth()).json()
    assert page["total"] == 1 and page["items"] == []
    detail = attendance_client.get("/exceptions/X-1", headers=auth()).json()
    listed = attendance_client.get("/exceptions", headers=auth()).json()
    assert detail["evidence_version"] == listed["items"][0]["evidence_version"]


def test_disabled_returns_unavailable(settings):
    with TestClient(
        create_app(settings, attendance_settings=AttendanceSettings(_env_file=None, enabled=False))
    ) as client:
        assert client.get("/exceptions", headers=auth()).status_code == 503


def test_no_write_endpoints(attendance_client):
    assert attendance_client.post("/exceptions/X-1", headers=auth(), json={}).status_code == 405
