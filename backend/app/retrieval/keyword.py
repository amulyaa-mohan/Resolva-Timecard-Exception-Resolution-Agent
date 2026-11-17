"""Version-filtered keyword retrieval (B-02). Hybrid keyword + vector search arrives in B-03.

Only clauses from the applicable pack and version are ever candidates, so a clause from
another jurisdiction or version cannot be retrieved, and therefore cannot be cited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.contracts import CaseContext, ExceptionCode, PolicyClause, PolicySnapshot

_TOKEN = re.compile(r"[a-z0-9]+")

QUERY_TERMS: dict[ExceptionCode, tuple[str, ...]] = {
    ExceptionCode.MISSING_PUNCH: (
        "missing",
        "punch",
        "clock",
        "scheduled",
        "inferred",
        "matching",
        "correction",
    ),
    ExceptionCode.OVERLAPPING_SHIFT: ("overlap", "shift", "punch", "correction", "working"),
    ExceptionCode.MEAL_BREAK_BREACH: ("rest", "interval", "break", "continuously", "hours"),
    ExceptionCode.OVERTIME_RISK: ("overtime", "daily", "weekly", "hours", "quarter", "limit"),
    ExceptionCode.SPREAD_OVER_BREACH: ("spread", "first", "last", "clock", "hours", "punching"),
    ExceptionCode.SCHEDULE_DEVIATION: ("late", "early", "arrival", "departure", "scheduled"),
}


@dataclass(frozen=True)
class RetrievedClause:
    clause: PolicyClause
    score: float


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def retrieve(
    case: CaseContext, policy: PolicySnapshot, top_k: int = 4, min_score: float = 2.0
) -> list[RetrievedClause]:
    """Top-k clauses from the applicable pack/version scoring at least min_score."""
    terms = set(QUERY_TERMS[case.code])
    scored = []
    for clause in policy.clauses:
        if clause.pack_id != policy.pack_id or clause.version != policy.version:
            continue  # defence in depth: never mix versions
        score = len(terms & _tokens(f"{clause.title} {clause.text}"))
        if score >= min_score:
            scored.append(RetrievedClause(clause, float(score)))
    scored.sort(key=lambda r: (-r.score, r.clause.clause_id))
    return scored[:top_k]
