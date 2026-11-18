"""Multilingual request understanding with an AI fallback chain (B-04).

1. Deterministic lexicon parser (works with AI off; guarantees parity on the supported commands).
2. If the lexicon recognises nothing and AI is enabled: LLM in JSON mode, validated against the
   `Intent` allow-list; any id it returns must appear verbatim in the request.
3. Otherwise: UNSUPPORTED (not_understood) with a localized hint.

Replies are rendered from fixed templates, so translation can never change facts: ids, exception
codes and policy citations stay canonical, and policy text is never translated.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.ai.pipeline import call_with_deadline
from app.ai.providers import ChatMessage, LLMProvider, ProviderRequest
from app.core.config import Settings
from app.core.contracts import ExceptionCode
from app.language.intents import (
    DateRange,
    Intent,
    IntentName,
    Language,
    UnsupportedReason,
    detect_language,
    parse_rules_scored,
)

INTENT_PROMPT_VERSION = "intent_v1"
MAX_REQUEST_CHARS = 500


@dataclass(frozen=True)
class IntentResult:
    language: Language
    method: Literal["rules", "llm", "none"]
    intent: Intent
    model_id: str | None = None
    latency_ms: int = 0
    error: str | None = None
    dropped_filters: tuple[str, ...] = ()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _llm_parse(
    text: str, provider: LLMProvider, settings: Settings
) -> tuple[Intent | None, str | None, str | None]:
    system = (settings.prompts_dir / f"{INTENT_PROMPT_VERSION}.md").read_text(encoding="utf-8")
    request = ProviderRequest(
        messages=(
            ChatMessage("system", system),
            ChatMessage("user", f"<request>{_escape(text)}</request>"),
        ),
        temperature=0.0,
        timeout_s=settings.llm_timeout_s,
    )
    try:
        response = call_with_deadline(provider, request)
    except Exception as exc:  # timeout, provider down, adapter bug: fall back safely
        return None, None, f"{type(exc).__name__}"
    try:
        data = json.loads(response.text)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        data = {k: v for k, v in data.items() if v is not None}
        intent = Intent.model_validate(data)
    except (ValueError, ValidationError) as exc:
        return None, response.model_id, f"invalid intent: {type(exc).__name__}"
    for value in (intent.exception_id, intent.employee_id):
        if value and value not in text:  # the model may not invent identifiers
            return None, response.model_id, "invented identifier"
    return intent, response.model_id, None


# Filters that are explicit words, not interpretation: the model may not add them. Live finding:
# for "Who skipped lunch?" Qwen added severity=problem and status=open, which nobody asked for.
LEXICAL_FILTERS = ("severity", "status", "employee_id")


def _keep_stated_filters(
    intent: Intent, rules_intent: Intent | None
) -> tuple[Intent, tuple[str, ...]]:
    """Take lexical filters from the deterministic parse; drop any the model added on its own."""
    if intent.intent == IntentName.UNSUPPORTED:
        return intent, ()
    stated = {f: getattr(rules_intent, f) if rules_intent else None for f in LEXICAL_FILTERS}
    dropped = tuple(
        f
        for f in LEXICAL_FILTERS
        if getattr(intent, f) is not None and getattr(intent, f) != stated[f]
    )
    return intent.model_copy(update=stated), dropped


def understand(
    text: str, *, settings: Settings, provider: LLMProvider | None = None
) -> IntentResult:
    started = time.perf_counter()
    text = text[:MAX_REQUEST_CHARS]
    lang, rules_intent, confident = parse_rules_scored(text)
    if rules_intent is not None and confident:
        return IntentResult(lang, "rules", rules_intent)

    error = model_id = None
    if settings.ai_enabled and provider is not None:
        intent, model_id, error = _llm_parse(text, provider, settings)
        if intent is not None:
            intent, dropped = _keep_stated_filters(intent, rules_intent)
            ms = int((time.perf_counter() - started) * 1000)
            return IntentResult(lang, "llm", intent, model_id, ms, dropped_filters=dropped)

    ms = int((time.perf_counter() - started) * 1000)
    if rules_intent is not None:
        # Partial lexicon parse (e.g. only a date). The localized reply states exactly what was
        # understood, so the manager can see it is broader than the question.
        return IntentResult(lang, "rules", rules_intent, model_id, ms, error)
    fallback = Intent(intent=IntentName.UNSUPPORTED, reason=UnsupportedReason.NOT_UNDERSTOOD)
    return IntentResult(detect_language(text), "none", fallback, model_id, ms, error)


# ------------------------------------------------------------------------------- rendering

TYPE_LABELS: dict[str, dict[ExceptionCode, str]] = {
    "en": {
        ExceptionCode.MISSING_PUNCH: "missing punch",
        ExceptionCode.OVERLAPPING_SHIFT: "overlapping shift",
        ExceptionCode.MEAL_BREAK_BREACH: "meal-break breach",
        ExceptionCode.OVERTIME_RISK: "overtime risk",
        ExceptionCode.SPREAD_OVER_BREACH: "spread-over breach",
        ExceptionCode.SCHEDULE_DEVIATION: "schedule deviation",
    },
    "hi": {
        ExceptionCode.MISSING_PUNCH: "छूटा पंच",
        ExceptionCode.OVERLAPPING_SHIFT: "ओवरलैपिंग शिफ्ट",
        ExceptionCode.MEAL_BREAK_BREACH: "भोजन अवकाश उल्लंघन",
        ExceptionCode.OVERTIME_RISK: "ओवरटाइम जोखिम",
        ExceptionCode.SPREAD_OVER_BREACH: "स्प्रेड-ओवर उल्लंघन",
        ExceptionCode.SCHEDULE_DEVIATION: "समय-सारणी विचलन",
    },
    "kn": {
        ExceptionCode.MISSING_PUNCH: "ತಪ್ಪಿದ ಪಂಚ್",
        ExceptionCode.OVERLAPPING_SHIFT: "ಅತಿಕ್ರಮಿಸುವ ಶಿಫ್ಟ್",
        ExceptionCode.MEAL_BREAK_BREACH: "ಊಟದ ವಿರಾಮ ಉಲ್ಲಂಘನೆ",
        ExceptionCode.OVERTIME_RISK: "ಓವರ್‌ಟೈಮ್ ಅಪಾಯ",
        ExceptionCode.SPREAD_OVER_BREACH: "ಸ್ಪ್ರೆಡ್-ಓವರ್ ಉಲ್ಲಂಘನೆ",
        ExceptionCode.SCHEDULE_DEVIATION: "ವೇಳಾಪಟ್ಟಿ ವ್ಯತ್ಯಾಸ",
    },
}
RANGE_LABELS: dict[str, dict[DateRange, str]] = {
    "en": {
        DateRange.TODAY: "today",
        DateRange.YESTERDAY: "yesterday",
        DateRange.THIS_WEEK: "this week",
        DateRange.LAST_WEEK: "last week",
        DateRange.THIS_PAY_PERIOD: "this pay period",
    },
    "hi": {
        DateRange.TODAY: "आज",
        DateRange.YESTERDAY: "कल (बीता हुआ)",
        DateRange.THIS_WEEK: "इस हफ्ते",
        DateRange.LAST_WEEK: "पिछले हफ्ते",
        DateRange.THIS_PAY_PERIOD: "इस वेतन अवधि",
    },
    "kn": {
        DateRange.TODAY: "ಇಂದು",
        DateRange.YESTERDAY: "ನಿನ್ನೆ",
        DateRange.THIS_WEEK: "ಈ ವಾರ",
        DateRange.LAST_WEEK: "ಕಳೆದ ವಾರ",
        DateRange.THIS_PAY_PERIOD: "ಈ ವೇತನ ಅವಧಿ",
    },
}
EXCEPTIONS_WORD = {"en": "exceptions", "hi": "अपवाद", "kn": "ವಿನಾಯಿತಿಗಳು"}
SEVERITY_LABELS = {
    "en": {"problem": "problems", "warning": "warnings"},
    "hi": {"problem": "समस्या", "warning": "चेतावनी"},
    "kn": {"problem": "ಸಮಸ್ಯೆ", "warning": "ಎಚ್ಚರಿಕೆ"},
}
TEMPLATES = {
    "en": {
        "LIST": "Showing {what}.",
        "COUNT": "Counting {what}.",
        "COUNT_RESULT": "{n} {what}.",
        "SHOW": "Opening exception {id}.",
        "EXPLAIN": "Explaining exception {id}. Policy citations are shown in their original language.",
        "action_not_allowed": "Requests to approve, reject or change records are not accepted "
        "here. Open the exception and use Approve, Edit or Reject.",
        "not_understood": 'Sorry, I did not understand. Try: "Show today\'s missing punches".',
        "all": "all",
    },
    "hi": {
        "LIST": "{what} दिखाए जा रहे हैं।",
        "COUNT": "{what} गिने जा रहे हैं।",
        "COUNT_RESULT": "{what}: {n}",
        "SHOW": "अपवाद {id} खोला जा रहा है।",
        "EXPLAIN": "अपवाद {id} का कारण दिखाया जा रहा है। नीति उद्धरण मूल भाषा में दिखाए जाते हैं।",
        "action_not_allowed": "यहाँ से मंजूरी, अस्वीकृति या रिकॉर्ड बदलने के अनुरोध स्वीकार नहीं "
        "किए जाते। अपवाद खोलें और Approve, Edit या Reject का उपयोग करें।",
        "not_understood": 'क्षमा करें, मैं समझ नहीं पाया। उदाहरण: "आज के छूटे पंच दिखाओ"।',
        "all": "सभी",
    },
    "kn": {
        "LIST": "{what} ತೋರಿಸಲಾಗುತ್ತಿದೆ.",
        "COUNT": "{what} ಎಣಿಸಲಾಗುತ್ತಿದೆ.",
        "COUNT_RESULT": "{what}: {n}",
        "SHOW": "ವಿನಾಯಿತಿ {id} ತೆರೆಯಲಾಗುತ್ತಿದೆ.",
        "EXPLAIN": "ವಿನಾಯಿತಿ {id} ಕಾರಣವನ್ನು ತೋರಿಸಲಾಗುತ್ತಿದೆ. ನೀತಿ ಉಲ್ಲೇಖಗಳು ಮೂಲ ಭಾಷೆಯಲ್ಲೇ ಇರುತ್ತವೆ.",
        "action_not_allowed": "ಇಲ್ಲಿಂದ ಅನುಮೋದನೆ, ತಿರಸ್ಕಾರ ಅಥವಾ ದಾಖಲೆ ಬದಲಾವಣೆಯ ವಿನಂತಿಗಳನ್ನು "
        "ಸ್ವೀಕರಿಸಲಾಗುವುದಿಲ್ಲ. ವಿನಾಯಿತಿಯನ್ನು ತೆರೆದು Approve, Edit ಅಥವಾ Reject ಬಳಸಿ.",
        "not_understood": 'ಕ್ಷಮಿಸಿ, ಅರ್ಥವಾಗಲಿಲ್ಲ. ಉದಾಹರಣೆ: "ಇಂದಿನ ತಪ್ಪಿದ ಪಂಚ್‌ಗಳನ್ನು ತೋರಿಸಿ".',
        "all": "ಎಲ್ಲಾ",
    },
}


def describe(intent: Intent, lang: Language) -> str:
    """Localized description of the filters, keeping canonical codes in parentheses."""
    parts = []
    if intent.date_range:
        parts.append(RANGE_LABELS[lang][intent.date_range])
    if intent.exception_type:
        label = TYPE_LABELS[lang][intent.exception_type]
        parts.append(f"{label} ({intent.exception_type.value})")
    if intent.severity:
        parts.append(SEVERITY_LABELS[lang][intent.severity.value])
    if intent.status:
        parts.append(intent.status)
    if intent.employee_id:
        parts.append(intent.employee_id)
    if not parts:
        parts.append(TEMPLATES[lang]["all"])
    return " ".join(parts) + " " + EXCEPTIONS_WORD[lang]


def render(result: IntentResult, count: int | None = None) -> str:
    lang, intent = result.language, result.intent
    t = TEMPLATES[lang]
    if intent.intent == IntentName.UNSUPPORTED:
        return t[intent.reason.value]
    if intent.intent == IntentName.SHOW_EXCEPTION:
        return t["SHOW"].format(id=intent.exception_id)
    if intent.intent == IntentName.EXPLAIN_EXCEPTION:
        return t["EXPLAIN"].format(id=intent.exception_id)
    what = describe(intent, lang)
    if intent.intent == IntentName.COUNT_EXCEPTIONS and count is not None:
        return t["COUNT_RESULT"].format(n=count, what=what)
    key = "COUNT" if intent.intent == IntentName.COUNT_EXCEPTIONS else "LIST"
    return t[key].format(what=what)


class ExceptionQuery(BaseModel):
    """Filters Track A's exception list endpoint should apply. Language-neutral."""

    model_config = ConfigDict(frozen=True)

    exception_type: ExceptionCode | None = None
    severity: str | None = None
    status: str | None = None
    date_range: DateRange | None = None
    employee_id: str | None = None
    exception_id: str | None = None


def to_query(intent: Intent) -> ExceptionQuery | None:
    if intent.intent == IntentName.UNSUPPORTED:
        return None
    return ExceptionQuery(
        exception_type=intent.exception_type,
        severity=intent.severity.value if intent.severity else None,
        status=intent.status,
        date_range=intent.date_range,
        employee_id=intent.employee_id,
        exception_id=intent.exception_id,
    )


def resolve_dates(date_range: DateRange, today: date) -> tuple[date, date]:
    """Inclusive date bounds. Weeks start Monday. Pay periods are a Track A setting; the
    demo uses half-months (1st-15th, 16th-end) until the real calendar is agreed."""
    from datetime import timedelta

    if date_range == DateRange.TODAY:
        return today, today
    if date_range == DateRange.YESTERDAY:
        y = today - timedelta(days=1)
        return y, y
    if date_range == DateRange.THIS_WEEK:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if date_range == DateRange.LAST_WEEK:
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    start = today.replace(day=1 if today.day <= 15 else 16)
    if today.day <= 15:
        return start, today.replace(day=15)
    nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, nxt - timedelta(days=1)
