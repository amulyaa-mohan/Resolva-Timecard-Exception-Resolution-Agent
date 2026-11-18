"""Draft domain DTOs for track A; not database models or frozen API contracts."""

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class DomainRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Employee(DomainRecord):
    id: str = Field(min_length=1)
    manager_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    timezone: str

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be an IANA timezone") from exc
        return value


class ScheduledShift(DomainRecord):
    id: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def chronological(self):
        if self.end <= self.start:
            raise ValueError("shift end must follow start")
        return self


class Punch(DomainRecord):
    id: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    event_time: AwareDatetime
    event_type: Literal["in", "out", "break_start", "break_end"]
    source: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)


class AttendanceCase(DomainRecord):
    employee: Employee
    schedule: ScheduledShift
    punches: tuple[Punch, ...]
    evidence_version: str = Field(min_length=1)
    as_of: AwareDatetime

    @model_validator(mode="after")
    def consistent(self):
        if self.schedule.employee_id != self.employee.id:
            raise ValueError("schedule belongs to another employee")
        ids, sources = set(), set()
        for punch in self.punches:
            if punch.employee_id != self.employee.id:
                raise ValueError("punch belongs to another employee")
            if punch.event_time > self.as_of:
                raise ValueError("future punches are not observed evidence")
            source_key = (punch.source, punch.source_event_id)
            if punch.id in ids or source_key in sources:
                raise ValueError("duplicate punch or source event")
            ids.add(punch.id)
            sources.add(source_key)
        return self
