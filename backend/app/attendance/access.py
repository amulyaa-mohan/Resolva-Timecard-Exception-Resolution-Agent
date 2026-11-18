"""Expiring server-provisioned demo credentials; replace with production identity provider."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class ManagerCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    manager_id: str = Field(min_length=1)
    token_sha256: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)
    expires_at: AwareDatetime
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value):
        ZoneInfo(value)
        return value


class AttendanceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ATTENDANCE_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )
    enabled: bool = False
    database_path: Path = BACKEND_DIR / "local" / "attendance.sqlite"
    credentials_path: Path = BACKEND_DIR / "local" / "manager-credentials.json"
    # PostgreSQL DSN. When set it replaces the demo SQLite file (database_path is ignored).
    database_url: str | None = Field(default=None, repr=False)


def read_credentials(path: Path) -> tuple[ManagerCredential, ...]:
    records = tuple(
        ManagerCredential.model_validate(record) for record in json.loads(path.read_text())
    )
    if len({r.token_sha256 for r in records}) != len(records):
        raise ValueError("Duplicate manager token digests")
    return records


bearer = HTTPBearer(auto_error=False)


def authenticated_manager(
    request: Request, auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> ManagerCredential:
    if not getattr(request.app.state, "attendance_repository", None):
        raise HTTPException(503, "Attendance demo is not configured.")
    if auth is None or auth.scheme.lower() != "bearer" or len(auth.credentials) > 1024:
        raise HTTPException(401, "Valid manager credentials required.")
    digest = hashlib.sha256(auth.credentials.encode()).hexdigest()
    now = datetime.now(UTC)
    for record in request.app.state.attendance_credentials:
        if hmac.compare_digest(record.token_sha256, digest) and record.expires_at > now:
            return record
    raise HTTPException(401, "Valid manager credentials required.")
