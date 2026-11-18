"""Lexical retrieval: tokenisation, exception-code query terms, and BM25 (B-02, extended in B-03)."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from app.core.contracts import CaseContext, ExceptionCode

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "may",
        "must",
        "not",
        "of",
        "on",
        "or",
        "the",
        "this",
        "to",
        "was",
        "were",
        "when",
        "with",
        "without",
    ]
)

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
    ExceptionCode.OVERLAPPING_SHIFT: ("overlap", "overlapping", "shift", "duplicate", "void"),
    ExceptionCode.MEAL_BREAK_BREACH: (
        "rest",
        "meal",
        "period",
        "interval",
        "break",
        "continuously",
    ),
    ExceptionCode.OVERTIME_RISK: ("overtime", "daily", "weekly", "hours", "quarter", "limit"),
    ExceptionCode.SPREAD_OVER_BREACH: ("spread", "span", "including", "intervals", "punching"),
    ExceptionCode.SCHEDULE_DEVIATION: ("late", "early", "arrival", "departure", "scheduled"),
}

# Natural-language intent per code, used by the vector side of hybrid retrieval.
QUERY_TEXT: dict[ExceptionCode, str] = {
    ExceptionCode.MISSING_PUNCH: "missing clock-in or clock-out punch inferred from the scheduled shift",
    ExceptionCode.OVERLAPPING_SHIFT: "two worked shifts overlap in time; duplicate or overlapping records",
    ExceptionCode.MEAL_BREAK_BREACH: "worked too long without the required meal period, meal break or rest interval",
    ExceptionCode.OVERTIME_RISK: "daily or weekly hours exceed the overtime threshold or quarterly cap",
    ExceptionCode.SPREAD_OVER_BREACH: "spread-over: total span of the working day exceeds the maximum spread",
    ExceptionCode.SCHEDULE_DEVIATION: "late arrival or early departure compared with the scheduled shift",
}


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


def query_tokens(case: CaseContext) -> list[str]:
    """Query from trusted fields only. Employee notes are untrusted and never steer retrieval."""
    words = list(QUERY_TERMS[case.code]) + tokens(QUERY_TEXT[case.code])
    for key in case.detection_details:
        words.extend(tokens(key.replace("_", " ")))
    return words


class BM25:
    """Okapi BM25 over a small, fixed corpus (one policy version's clauses)."""

    def __init__(self, documents: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(tokens(d)) for d in documents]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: Sequence[str]) -> list[float]:
        terms = set(query)
        out = []
        for doc, length in zip(self.docs, self.lengths, strict=True):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / self.avg_len) if self.avg_len else 0
            for t in terms:
                f = doc.get(t, 0)
                if f:
                    score += self.idf[t] * f * (self.k1 + 1) / (f + norm)
            out.append(score)
        return out
