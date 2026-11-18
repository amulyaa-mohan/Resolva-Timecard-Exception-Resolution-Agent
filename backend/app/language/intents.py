"""Language-neutral manager intents and the deterministic multilingual parser (B-04).

Every request, in any supported language, becomes one allow-listed `Intent`. The same intent
reaches the same deterministic API, so language never changes rule logic or results.

The language layer is READ-ONLY: listing, counting, showing and explaining exceptions. Requests
to approve, reject, edit or delete are refused in every language; decisions stay in the
authorised manager workflow (Track A), never in free text.

Lexicons cover a tested demo command set in English, Kannada and Hindi. They were written for the
prototype and need review by native speakers before any real use.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.contracts import ExceptionCode, Severity

Language = Literal["en", "hi", "kn"]


class IntentName(StrEnum):
    LIST_EXCEPTIONS = "LIST_EXCEPTIONS"
    COUNT_EXCEPTIONS = "COUNT_EXCEPTIONS"
    SHOW_EXCEPTION = "SHOW_EXCEPTION"
    EXPLAIN_EXCEPTION = "EXPLAIN_EXCEPTION"
    UNSUPPORTED = "UNSUPPORTED"


class DateRange(StrEnum):
    TODAY = "TODAY"
    YESTERDAY = "YESTERDAY"
    THIS_WEEK = "THIS_WEEK"
    LAST_WEEK = "LAST_WEEK"
    THIS_PAY_PERIOD = "THIS_PAY_PERIOD"


class UnsupportedReason(StrEnum):
    ACTION_NOT_ALLOWED = "action_not_allowed"  # approve/reject/edit/delete via chat
    NOT_UNDERSTOOD = "not_understood"


EXCEPTION_ID = r"X-[A-Za-z0-9][A-Za-z0-9-]{0,39}"
EMPLOYEE_ID = r"E-[A-Za-z0-9][A-Za-z0-9-]{0,39}"


class Intent(BaseModel):
    """Strict, language-neutral request. Validated before any backend call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: IntentName
    exception_type: ExceptionCode | None = None
    severity: Severity | None = None
    status: Literal["open", "escalated"] | None = None
    date_range: DateRange | None = None
    exception_id: str | None = Field(default=None, pattern=f"^{EXCEPTION_ID}$")
    employee_id: str | None = Field(default=None, pattern=f"^{EMPLOYEE_ID}$")
    reason: UnsupportedReason | None = None

    @model_validator(mode="after")
    def _shape(self) -> Intent:
        single = self.intent in (IntentName.SHOW_EXCEPTION, IntentName.EXPLAIN_EXCEPTION)
        if single and not self.exception_id:
            raise ValueError(f"{self.intent.value} requires exception_id")
        if self.intent in (IntentName.LIST_EXCEPTIONS, IntentName.COUNT_EXCEPTIONS) and (
            self.exception_id
        ):
            raise ValueError("list/count intents filter; they do not take an exception_id")
        if self.intent == IntentName.UNSUPPORTED:
            if self.reason is None:
                raise ValueError("UNSUPPORTED requires a reason")
        elif self.reason is not None:
            raise ValueError("reason is only for UNSUPPORTED")
        return self


# ------------------------------------------------------------------------------- normalisation

_INVISIBLE = dict.fromkeys(map(ord, "‌‍﻿"), None)  # ZWNJ, ZWJ, BOM


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    return " ".join(text.lower().split())


def detect_language(text: str) -> Language:
    """By script: Kannada (U+0C80-0CFF), Devanagari for Hindi (U+0900-097F), else English."""
    kn = sum("ಀ" <= ch <= "೿" for ch in text)
    hi = sum("ऀ" <= ch <= "ॿ" for ch in text)
    if kn == 0 and hi == 0:
        return "en"
    return "kn" if kn >= hi else "hi"


# ------------------------------------------------------------------------------- lexicons
# Phrases are matched after normalise(). Latin phrases match on word boundaries; Indic phrases
# match as substrings so inflected forms (e.g. ಪಂಚ್‌ಗಳನ್ನು, पंचों) still match their stem.

WRITE_ACTIONS = {
    "en": [
        "approve",
        "reject",
        "delete",
        "remove",
        "edit",
        "change",
        "modify",
        "update",
        "add",
        "apply",
        "fix",
        "void",
        "override",
    ],
    "hi": [
        "मंजूर",
        "मंज़ूर",
        "स्वीकृत करो",
        "स्वीकार करो",
        "अस्वीकार",
        "हटाओ",
        "हटा दो",
        "बदलो",
        "बदल दो",
        "जोड़ो",
        "जोड़ दो",
        "ठीक करो",
    ],
    "kn": ["ಅನುಮೋದಿಸಿ", "ಅನುಮೋದಿಸು", "ತಿರಸ್ಕರಿಸಿ", "ಅಳಿಸಿ", "ಅಳಿಸು", "ಬದಲಾಯಿಸಿ", "ಸೇರಿಸಿ", "ಸರಿಪಡಿಸಿ"],
}

COUNT_WORDS = {
    "en": ["how many", "count", "number of"],
    "hi": ["कितने", "कितनी", "कितना", "संख्या"],
    "kn": ["ಎಷ್ಟು", "ಸಂಖ್ಯೆ"],
}
EXPLAIN_WORDS = {
    "en": ["why", "explain", "reason"],
    "hi": ["क्यों", "समझाओ", "समझाइए", "कारण"],
    "kn": ["ಏಕೆ", "ಯಾಕೆ", "ವಿವರಿಸಿ", "ಕಾರಣ"],
}
SHOW_WORDS = {
    "en": ["show", "list", "find", "open", "display", "which", "what are"],
    "hi": ["दिखाओ", "दिखाइए", "दिखाएं", "सूची", "बताओ", "बताइए", "कौन"],
    "kn": ["ತೋರಿಸಿ", "ತೋರಿಸು", "ಪಟ್ಟಿ", "ತಿಳಿಸಿ", "ಯಾವ"],
}

EXCEPTION_TYPES: dict[ExceptionCode, dict[str, list[str]]] = {
    ExceptionCode.MISSING_PUNCH: {
        "en": [
            "missing punch",
            "missed punch",
            "missing clock",
            "forgot to punch",
            "forgot to clock",
            "missing punches",
            "missed punches",
        ],
        "hi": ["छूटे पंच", "छूटा पंच", "छूटी पंच", "मिसिंग पंच", "पंच छूट", "पंच नहीं"],
        "kn": ["ತಪ್ಪಿದ ಪಂಚ್", "ಮಿಸ್ಸಿಂಗ್ ಪಂಚ್", "ಪಂಚ್ ತಪ್ಪಿ", "ಪಂಚ್ ಮಾಡದ"],
    },
    ExceptionCode.OVERTIME_RISK: {
        "en": ["overtime"],
        "hi": ["ओवरटाइम", "अतिरिक्त समय"],
        "kn": ["ಓವರ್ಟೈಮ್", "ಹೆಚ್ಚುವರಿ ಸಮಯ"],
    },
    ExceptionCode.MEAL_BREAK_BREACH: {
        "en": ["meal break", "missed break", "rest break", "break breach"],
        "hi": ["भोजन अवकाश", "भोजन विराम", "ब्रेक नहीं"],
        "kn": ["ಊಟದ ವಿರಾಮ", "ವಿರಾಮ ತಪ್ಪಿ"],
    },
    ExceptionCode.OVERLAPPING_SHIFT: {
        "en": ["overlapping shift", "overlap"],
        "hi": ["ओवरलैप", "दोहरी शिफ्ट"],
        "kn": ["ಓವರ್ಲ್ಯಾಪ್", "ಅತಿಕ್ರಮಿಸುವ ಶಿಫ್ಟ್"],
    },
    ExceptionCode.SPREAD_OVER_BREACH: {
        "en": ["spread-over", "spread over", "spreadover"],
        "hi": ["स्प्रेड-ओवर", "स्प्रेड ओवर"],
        "kn": ["ಸ್ಪ್ರೆಡ್-ಓವರ್", "ಸ್ಪ್ರೆಡ್ ಓವರ್"],
    },
    ExceptionCode.SCHEDULE_DEVIATION: {
        "en": ["late arrival", "early departure", "schedule deviation", "came late", "left early"],
        "hi": ["देर से आए", "देर से आने", "जल्दी गए", "जल्दी जाने"],
        "kn": ["ತಡವಾಗಿ ಬಂದ", "ಬೇಗ ಹೋದ"],
    },
}

DATE_RANGES: dict[DateRange, dict[str, list[str]]] = {
    DateRange.TODAY: {"en": ["today"], "hi": ["आज"], "kn": ["ಇಂದು", "ಇವತ್ತು", "ಇಂದಿನ"]},
    DateRange.YESTERDAY: {"en": ["yesterday"], "hi": ["बीते कल", "कल के", "कल"], "kn": ["ನಿನ್ನೆ"]},
    DateRange.THIS_WEEK: {"en": ["this week"], "hi": ["इस हफ्ते", "इस सप्ताह"], "kn": ["ಈ ವಾರ"]},
    DateRange.LAST_WEEK: {
        "en": ["last week", "previous week"],
        "hi": ["पिछले हफ्ते", "पिछले सप्ताह"],
        "kn": ["ಕಳೆದ ವಾರ"],
    },
    DateRange.THIS_PAY_PERIOD: {
        "en": ["this pay period", "pay period"],
        "hi": ["इस वेतन अवधि", "वेतन अवधि", "पे पीरियड"],
        "kn": ["ಈ ವೇತನ ಅವಧಿ", "ವೇತನ ಅವಧಿ"],
    },
}

SEVERITIES: dict[Severity, dict[str, list[str]]] = {
    Severity.PROBLEM: {"en": ["problem", "problems"], "hi": ["समस्या"], "kn": ["ಸಮಸ್ಯೆ"]},
    Severity.WARNING: {"en": ["warning", "warnings"], "hi": ["चेतावनी"], "kn": ["ಎಚ್ಚರಿಕೆ"]},
}

STATUSES = {
    "escalated": {"en": ["escalated"], "hi": ["एस्केलेट"], "kn": ["ಎಸ್ಕಲೇಟ್"]},
    "open": {
        "en": ["open exceptions", "unresolved", "pending"],
        "hi": ["लंबित", "बाकी"],
        "kn": ["ಬಾಕಿ"],
    },
}


# Letters and combining marks of the Devanagari and Kannada blocks.
_INDIC = "ऀ-ॿಀ-೿"
# Indic words this short also occur inside unrelated words (e.g. Hindi "कल", yesterday, inside
# "निकल", left, and "सकल", total), so they must match as whole words.
_SHORT_INDIC = 3


def _has(text: str, phrases: list[str], lang: str) -> bool:
    for phrase in phrases:
        p = normalise(phrase)
        if lang == "en" or p.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", text):
                return True
            continue
        # Start on a word boundary; allow suffixes (ಪಂಚ್‌ಗಳನ್ನು, पंचों) except for short words.
        end = rf"(?![{_INDIC}])" if len(p) <= _SHORT_INDIC and " " not in p else ""
        if re.search(rf"(?<![{_INDIC}]){re.escape(p)}{end}", text):
            return True
    return False


def _first(text: str, table: dict, lang: str):
    for key, by_lang in table.items():
        # English loanwords (e.g. "overtime") are common in Hindi/Kannada messages too.
        if _has(text, by_lang.get(lang, []), lang) or _has(text, by_lang["en"], "en"):
            return key
    return None


def _any_lang(text: str, words: dict[str, list[str]], lang: str) -> bool:
    return _has(text, words.get(lang, []), lang) or _has(text, words["en"], "en")


def parse_rules(text: str) -> tuple[Language, Intent | None]:
    """Deterministic parse: (language, intent), or (language, None) if nothing was recognised."""
    lang, intent, _ = parse_rules_scored(text)
    return lang, intent


def parse_rules_scored(text: str) -> tuple[Language, Intent | None, bool]:
    """Deterministic parse plus whether it is confident.

    Confident means the lexicon recognised something specific: a write verb, an exception id, an
    exception type, a severity or a status. A parse built only from a date range (e.g. "anyone who
    didn't punch out today?" -> "today") would silently drop the request's real meaning, so it is
    not confident and the AI fallback gets a chance first.
    """
    lang = detect_language(text)
    norm = normalise(text)

    if _any_lang(norm, WRITE_ACTIONS, lang):
        refused = Intent(intent=IntentName.UNSUPPORTED, reason=UnsupportedReason.ACTION_NOT_ALLOWED)
        return lang, refused, True

    # Ids must not be glued to a preceding token: "TAX-2026" is not X-2026, "TIME-OFF" not E-OFF.
    exception_id = next(iter(re.findall(rf"(?<![A-Za-z0-9-]){EXCEPTION_ID}", text)), None)
    employee_id = next(iter(re.findall(rf"(?<![A-Za-z0-9-]){EMPLOYEE_ID}", text)), None)
    filters = {
        "exception_type": _first(norm, EXCEPTION_TYPES, lang),
        "date_range": _first(norm, DATE_RANGES, lang),
        "severity": _first(norm, SEVERITIES, lang),
        "status": _first(norm, STATUSES, lang),
        "employee_id": employee_id,
    }

    if exception_id:
        name = (
            IntentName.EXPLAIN_EXCEPTION
            if _any_lang(norm, EXPLAIN_WORDS, lang)
            else IntentName.SHOW_EXCEPTION
        )
        return lang, Intent(intent=name, exception_id=exception_id), True

    if not any(v is not None for v in filters.values()):
        return lang, None, False  # nothing recognised: let the LLM try, or report not understood

    name = (
        IntentName.COUNT_EXCEPTIONS
        if _any_lang(norm, COUNT_WORDS, lang)
        else IntentName.LIST_EXCEPTIONS
    )
    specific = any(filters[k] is not None for k in ("exception_type", "severity", "status"))
    return lang, Intent(intent=name, **filters), specific
