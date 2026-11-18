"""CSV/JSON attendance import preview (A-05): field mapping, timezone normalization, dedupe.

Pure functions; nothing is written here. Imported content is untrusted data: it is parsed,
validated and never interpreted as instructions. Equivalent CSV and JSON inputs produce
identical records (same ids, same UTC instants), so rule outcomes are identical too.
"""

import csv
import hashlib
import io
import json
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.core.contracts import PunchRecord, PunchSource, PunchType, ScheduledShift

MAX_ROWS = 5000
MAX_BYTES = 2_000_000
MAX_CELL_CHARS = 4000  # no real field is longer; a note is capped lower, at MAX_NOTE_CHARS
MAX_BREAK_MIN = 24 * 60  # also keeps the value inside PostgreSQL's 32-bit integer
# Timestamps outside these years are data-entry errors, and the extremes overflow the timezone
# arithmetic the rest of the pipeline depends on.
MIN_YEAR, MAX_YEAR = 2000, 2100

PUNCH_FIELDS = (
    "employee_id",
    "timestamp",
    "date",
    "time",
    "type",
    "source",
    "device_id",
    "source_event_id",
)
SHIFT_FIELDS = ("employee_id", "shift_id", "start", "end", "planned_break_min")
NOTE_FIELDS = ("employee_id", "text", "submitted_at", "note_id")
MAX_NOTE_CHARS = 1000  # matches the employee_notes CHECK and the EmployeeNote contract

TYPE_ALIASES = {
    "in": PunchType.IN,
    "clock_in": PunchType.IN,
    "clockin": PunchType.IN,
    "punch_in": PunchType.IN,
    "out": PunchType.OUT,
    "clock_out": PunchType.OUT,
    "clockout": PunchType.OUT,
    "punch_out": PunchType.OUT,
    "break_start": PunchType.BREAK_START,
    "start_break": PunchType.BREAK_START,
    "meal_start": PunchType.BREAK_START,
    "break_end": PunchType.BREAK_END,
    "end_break": PunchType.BREAK_END,
    "meal_end": PunchType.BREAK_END,
}


class ImportFileError(ValueError):
    """The file itself is unreadable (not one bad row)."""


class NoteRecord(BaseModel):
    """An employee's own words about a work day. Untrusted text: it is stored and shown,
    and only ever read by the model as quoted evidence, never as an instruction."""

    note_id: str
    employee_id: str
    text: str
    submitted_at: datetime


class PreviewRow(BaseModel):
    row_number: int = Field(description="1-based data row (CSV header excluded).")
    status: Literal["valid", "invalid", "duplicate"]
    error: str | None = None
    duplicate_of: int | None = Field(default=None, description="Earlier row in this file.")
    punch: PunchRecord | None = None
    source_event_id: str | None = Field(default=None, description="Given or derived dedupe id.")
    shift: ScheduledShift | None = None
    note: NoteRecord | None = None


class ImportPreview(BaseModel):
    kind: Literal["punches", "shifts", "notes"]
    rows: list[PreviewRow]
    valid: int
    invalid: int
    duplicates: int


def read_rows(content: str, fmt: Literal["csv", "json"]) -> list[dict[str, str]]:
    """Parse untrusted text into rows. Every way the text can be malformed, including ways the
    standard library reports as an unrelated exception type, becomes an ImportFileError."""
    if len(content.encode()) > MAX_BYTES:
        raise ImportFileError(f"file larger than {MAX_BYTES} bytes")
    if "\x00" in content:
        # PostgreSQL text cannot hold a NUL byte, so it would fail later, at insert time.
        raise ImportFileError("file contains a NUL byte")
    if fmt == "csv":
        try:
            reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
            if not reader.fieldnames:
                raise ImportFileError("CSV has no header row")
            rows = list(reader)
        except csv.Error as exc:
            raise ImportFileError(f"invalid CSV: {exc}") from exc
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ImportFileError(f"invalid JSON: {exc.msg}") from exc
        except RecursionError as exc:
            raise ImportFileError("JSON is nested too deeply") from exc
        except ValueError as exc:  # e.g. an integer with thousands of digits
            raise ImportFileError("JSON contains a number that is too large") from exc
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            data = data["rows"]
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise ImportFileError('JSON must be a list of objects (or {"rows": [...]})')
        rows = data
    if len(rows) > MAX_ROWS:
        raise ImportFileError(f"more than {MAX_ROWS} rows")
    cleaned = [
        {str(k).strip(): "" if v is None else str(v).strip() for k, v in row.items() if k}
        for row in rows
    ]
    # JSON can spell a NUL as an escape, which only exists after decoding.
    if any("\x00" in k or "\x00" in v for row in cleaned for k, v in row.items()):
        raise ImportFileError("file contains a NUL byte")
    if any(len(v) > MAX_CELL_CHARS for row in cleaned for v in row.values()):
        raise ImportFileError(f"a cell is longer than {MAX_CELL_CHARS} characters")
    return cleaned


def _instant(value: str, zone: ZoneInfo) -> datetime:
    """Aware instant. Naive local times use the employee's zone; DST gaps/overlaps refused."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise ValueError(f"timestamp year must be between {MIN_YEAR} and {MAX_YEAR}")
    if parsed.tzinfo is not None:
        return parsed
    first, second = parsed.replace(tzinfo=zone, fold=0), parsed.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError(f"local time {value} is ambiguous or does not exist (DST change)")
    return first


def _break_minutes(value: str) -> int:
    minutes = int(value or 0)
    if not 0 <= minutes <= MAX_BREAK_MIN:
        raise ValueError(f"planned_break_min must be between 0 and {MAX_BREAK_MIN}")
    return minutes


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def preview_punches(
    rows: list[dict[str, str]],
    *,
    employee_timezones: dict[str, str],
    mapping: dict[str, str] | None = None,
    existing_keys: frozenset[tuple[str, str]] = frozenset(),
) -> ImportPreview:
    """employee_timezones lists the employees this importer may write (authorization)."""
    mapping = mapping or {}
    seen: dict[tuple, int] = {}
    out: list[PreviewRow] = []
    for number, row in enumerate(rows, 1):

        def get(field: str, row=row) -> str:
            return row.get(mapping.get(field, field), "")

        try:
            employee = get("employee_id")
            if employee not in employee_timezones:
                raise ValueError("unknown employee, or not assigned to you")
            zone = ZoneInfo(employee_timezones[employee])
            kind = TYPE_ALIASES.get(get("type").lower().replace(" ", "_").replace("-", "_"))
            if kind is None:
                raise ValueError(f"unknown punch type {get('type')!r}")
            stamp = get("timestamp") or (
                f"{get('date')}T{get('time')}" if get("date") and get("time") else ""
            )
            if not stamp:
                raise ValueError("timestamp (or date and time) required")
            ts = _instant(stamp, zone)
            source = PunchSource((get("source") or "import").lower())
            event_id = get("source_event_id") or "derived:" + _digest(
                employee, ts.astimezone(ZoneInfo("UTC")).isoformat(), kind.value
            )
            punch = PunchRecord(
                punch_id="PI-" + _digest(source.value, event_id),
                employee_id=employee,
                ts=ts,
                type=kind,
                source=source,
                device_id=get("device_id") or None,
            )
        except ValueError as exc:
            out.append(PreviewRow(row_number=number, status="invalid", error=str(exc)))
            continue
        keys = [(source.value, event_id), (employee, ts.timestamp(), kind.value)]
        earlier = next((seen[k] for k in keys if k in seen), None)
        if earlier is not None:
            out.append(
                PreviewRow(
                    row_number=number,
                    status="duplicate",
                    duplicate_of=earlier,
                    error="same punch earlier in this file",
                )
            )
            continue
        if (source.value, event_id) in existing_keys:
            # Keep the record: a retry after a failed detection must still re-check its date.
            out.append(
                PreviewRow(
                    row_number=number,
                    status="duplicate",
                    error="already imported",
                    punch=punch,
                    source_event_id=event_id,
                )
            )
            continue
        for key in keys:
            seen[key] = number
        out.append(
            PreviewRow(row_number=number, status="valid", punch=punch, source_event_id=event_id)
        )
    return _summary("punches", out)


def preview_shifts(
    rows: list[dict[str, str]],
    *,
    employee_timezones: dict[str, str],
    mapping: dict[str, str] | None = None,
) -> ImportPreview:
    mapping = mapping or {}
    seen: dict[tuple, int] = {}
    out: list[PreviewRow] = []
    for number, row in enumerate(rows, 1):

        def get(field: str, row=row) -> str:
            return row.get(mapping.get(field, field), "")

        try:
            employee = get("employee_id")
            if employee not in employee_timezones:
                raise ValueError("unknown employee, or not assigned to you")
            zone = ZoneInfo(employee_timezones[employee])
            start, end = _instant(get("start"), zone), _instant(get("end"), zone)
            if end <= start:
                raise ValueError("shift end must be after its start")
            shift = ScheduledShift(
                shift_id=get("shift_id") or "SI-" + _digest(employee, start.isoformat()),
                employee_id=employee,
                start=start,
                end=end,
                planned_break_min=_break_minutes(get("planned_break_min")),
            )
        except ValueError as exc:
            out.append(PreviewRow(row_number=number, status="invalid", error=str(exc)))
            continue
        key = (employee, start.timestamp())
        if key in seen or (shift.shift_id,) in seen:
            out.append(
                PreviewRow(
                    row_number=number,
                    status="duplicate",
                    duplicate_of=seen.get(key) or seen.get((shift.shift_id,)),
                    error="same shift earlier in this file",
                )
            )
            continue
        seen[key] = seen[(shift.shift_id,)] = number
        out.append(PreviewRow(row_number=number, status="valid", shift=shift))
    return _summary("shifts", out)


def preview_notes(
    rows: list[dict[str, str]],
    *,
    employee_timezones: dict[str, str],
    mapping: dict[str, str] | None = None,
    existing_ids: frozenset[str] = frozenset(),
) -> ImportPreview:
    """Employee notes. The id is derived from the employee and content, so re-importing the same
    file is a no-op, and one employee's id can never collide with another employee's note."""
    mapping = mapping or {}
    seen: dict[str, int] = {}
    out: list[PreviewRow] = []
    for number, row in enumerate(rows, 1):

        def get(field: str, row=row) -> str:
            return row.get(mapping.get(field, field), "")

        try:
            employee = get("employee_id")
            if employee not in employee_timezones:
                raise ValueError("unknown employee, or not assigned to you")
            text = get("text")
            if not text:
                raise ValueError("note text is required")
            if len(text) > MAX_NOTE_CHARS:
                raise ValueError(f"note is longer than {MAX_NOTE_CHARS} characters")
            if not get("submitted_at"):
                raise ValueError("submitted_at is required")
            submitted = _instant(get("submitted_at"), ZoneInfo(employee_timezones[employee]))
            key = get("note_id") or submitted.astimezone(ZoneInfo("UTC")).isoformat() + "|" + text
            note = NoteRecord(
                note_id="NI-" + _digest(employee, key),
                employee_id=employee,
                text=text,
                submitted_at=submitted,
            )
        except ValueError as exc:
            out.append(PreviewRow(row_number=number, status="invalid", error=str(exc)))
            continue
        if note.note_id in seen:
            out.append(
                PreviewRow(
                    row_number=number,
                    status="duplicate",
                    duplicate_of=seen[note.note_id],
                    error="same note earlier in this file",
                )
            )
            continue
        if note.note_id in existing_ids:
            out.append(
                PreviewRow(
                    row_number=number, status="duplicate", error="already imported", note=note
                )
            )
            continue
        seen[note.note_id] = number
        out.append(PreviewRow(row_number=number, status="valid", note=note))
    return _summary("notes", out)


def _summary(kind, rows: list[PreviewRow]) -> ImportPreview:
    count = {s: sum(r.status == s for r in rows) for s in ("valid", "invalid", "duplicate")}
    return ImportPreview(
        kind=kind,
        rows=rows,
        valid=count["valid"],
        invalid=count["invalid"],
        duplicates=count["duplicate"],
    )


def local_dates(preview: ImportPreview, employee_timezones: dict[str, str]) -> dict[str, set[date]]:
    """Employee -> local dates whose detection must re-run.

    Rows already in the database count too: the import commits before detection runs, so if
    detection failed the first time, a retry sees every row as already imported and would
    otherwise never re-check those dates. Re-detecting is idempotent, so the cost is only time.
    """
    touched: dict[str, set[date]] = {}
    for row in preview.rows:
        record = row.punch or row.shift
        counts = row.status == "valid" or (row.status == "duplicate" and record is not None)
        if not counts or record is None:
            continue  # notes do not change which rules fire, so they touch no dates
        zone = ZoneInfo(employee_timezones[record.employee_id])
        at = record.ts if row.punch else record.start
        touched.setdefault(record.employee_id, set()).add(at.astimezone(zone).date())
    return touched
