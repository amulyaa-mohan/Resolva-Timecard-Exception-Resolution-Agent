"""Deterministic offline provider for tests, CI, and AI-free demos.

It reads only the prompt text, exactly like a real model, so it exercises the same
prompt-building and parsing path. It is a stand-in, not a measure of model quality.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timedelta

from app.ai.providers.base import ProviderError, ProviderRequest, ProviderResponse

_CASE_RE = re.compile(r"<case_json>(.*?)</case_json>", re.DOTALL)
_CLAUSES_RE = re.compile(r"<retrieved_clauses_json>(.*?)</retrieved_clauses_json>", re.DOTALL)
_NOTE_RE = re.compile(r"<untrusted_note[^>]*>(.*?)</untrusted_note>", re.DOTALL)
# Codes fixed only by moving a recorded punch to a time the employee stated (step 2).
_ADJUST_CODES = {
    "SCHEDULE_DEVIATION": "late",
    "SPREAD_OVER_BREACH": "spread",
    "OVERLAPPING_SHIFT": "overlap",
}
_ADJUST_WINDOW = timedelta(minutes=30)


class MockProvider:
    name = "mock"

    def __init__(
        self,
        model_id: str = "mock-resolver-v1",
        script: Iterable[str | Exception] | None = None,
    ) -> None:
        """With a script, return (or raise) each item in order instead of drafting."""
        self.model_id = model_id
        self._script = list(script) if script is not None else None
        self.calls: list[ProviderRequest] = []

    def is_reachable(self) -> bool:
        return True

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if self._script is not None:
            if not self._script:
                raise ProviderError("mock script exhausted")
            item = self._script.pop(0)
            if isinstance(item, Exception):
                raise item
            return ProviderResponse(text=item, model_id=self.model_id)
        user = next(m.content for m in reversed(request.messages) if m.role == "user")
        return ProviderResponse(text=json.dumps(self._draft(user)), model_id=self.model_id)

    # ------------------------------------------------------------------ drafting

    def _draft(self, prompt: str) -> dict:
        case_match, clauses_match = _CASE_RE.search(prompt), _CLAUSES_RE.search(prompt)
        if not case_match or not clauses_match:
            raise ProviderError("prompt missing case or clause sections")
        case = json.loads(case_match.group(1))
        clauses = json.loads(clauses_match.group(1))
        exception_id = case["exception_id"]

        if case["code"] in _ADJUST_CODES and clauses:
            return _draft_adjustment(case, clauses, prompt)
        if case["code"] != "MISSING_PUNCH":
            return _escalate(exception_id, "Mock provider drafts MISSING_PUNCH fixes only.")
        schedule = case.get("schedule")
        if schedule is None:
            return _escalate(
                exception_id,
                "No scheduled shift exists, so a missing punch time cannot be inferred.",
                ["Scheduled shift for the work date", "Employee note with the actual time"],
            )
        if not clauses:
            return _escalate(exception_id, "No applicable policy clause was retrieved.")

        types = [p["type"] for p in case["punches"]]
        if types.count("in") > types.count("out"):
            punch_type, new_ts, label = "out", schedule["end"], "clock-out"
        elif types.count("out") > types.count("in"):
            punch_type, new_ts, label = "in", schedule["start"], "clock-in"
        else:
            return _escalate(exception_id, "Punches are paired; the missing punch is ambiguous.")

        clause = next((c for c in clauses if "missing" in c["text"].lower()), clauses[0])
        return {
            "exception_id": exception_id,
            "decision": "propose",
            "actions": [
                {
                    "type": "add_punch",
                    "punch_type": punch_type,
                    "new_ts": new_ts,
                    "note": f"Add missing {label} at the scheduled time.",
                }
            ],
            "rationale": (
                f"The employee has an unmatched punch and the {label} is missing. "
                f"Policy allows inferring it from the scheduled shift ({clause['clause_id']})."
            ),
            "citations": [{"chunk_id": clause["chunk_id"], "quote": _first_sentence(clause)}],
            "confidence": 0.86,
            "missing_information": [],
        }


def _escalate(exception_id: str, rationale: str, missing: list[str] | None = None) -> dict:
    return {
        "exception_id": exception_id,
        "decision": "escalate",
        "actions": [],
        "rationale": rationale,
        "citations": [],
        "confidence": 0.0,
        "missing_information": missing or [rationale],
    }


def _first_sentence(clause: dict) -> str:
    text = " ".join(clause["text"].split())
    end = text.find(". ")
    return (text if end == -1 else text[: end + 1])[:300]


def _draft_adjustment(case: dict, clauses: list[dict], prompt: str) -> dict:
    """Move the recorded work punch closest to a stated time onto that time (within 30 min)."""
    from app.ai.evidence import note_times  # local import: providers stay free of AI-layer deps

    stated = [t for note in _NOTE_RE.findall(prompt) for t in note_times(note)]
    best = None
    # An overlap is fixed by ending the earlier session sooner, so only clock-outs are candidates.
    movable = ("out",) if case["code"] == "OVERLAPPING_SHIFT" else ("in", "out")
    for punch in case["punches"]:
        if punch["type"] not in movable:
            continue
        ts = datetime.fromisoformat(punch["ts"])
        for hour, minute in stated:
            for days in (-1, 0, 1):
                candidate = ts.replace(hour=hour, minute=minute, second=0) + timedelta(days=days)
                gap = abs(candidate - ts)
                if timedelta(0) < gap <= _ADJUST_WINDOW and (best is None or gap < best[0]):
                    best = (gap, punch, candidate)
    exception_id = case["exception_id"]
    if best is None:
        return _escalate(exception_id, "No stated time describes a punching error.")
    _, punch, new_ts = best
    keyword = _ADJUST_CODES[case["code"]]
    clause = next((c for c in clauses if keyword in c["text"].lower()), clauses[0])
    return {
        "exception_id": exception_id,
        "decision": "propose",
        "actions": [
            {
                "type": "adjust_punch",
                "punch_id": punch["punch_id"],
                "punch_type": None,
                "new_ts": new_ts.isoformat(),
                "note": "Correct the recording error to the time the employee stated.",
            }
        ],
        "rationale": (
            f"The employee stated {new_ts:%H:%M}, which describes a punching error on "
            f"{punch['punch_id']} ({clause['clause_id']})."
        ),
        "citations": [{"chunk_id": clause["chunk_id"], "quote": _first_sentence(clause)}],
        "confidence": 0.82,
        "missing_information": [],
    }
