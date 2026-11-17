"""B-04 acceptance: English/Kannada/Hindi intent parity and a verified rules-only path."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai.providers import MockProvider, ProviderTimeout
from app.language.assistant import render, resolve_dates, to_query, understand
from app.language.intents import DateRange, Intent, detect_language, normalise, parse_rules
from app.main import create_app
from evals.language_eval import EVALS_DIR, eval_language

CASES = json.loads((EVALS_DIR / "language_cases.json").read_text("utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_lexicon_parity_across_languages(case):
    intents = {}
    for lang in ("en", "hi", "kn"):
        detected, intent = parse_rules(case[lang])
        assert detected == lang
        assert intent is not None, f"{lang}: {case[lang]!r} not understood"
        intents[lang] = intent.model_dump(mode="json", exclude_none=True)
        assert intents[lang] == case["expected"], (lang, case[lang])
    assert intents["en"] == intents["hi"] == intents["kn"]


def test_rules_only_path_needs_no_model(settings):
    off = settings.model_copy(update={"ai_enabled": False})
    report = eval_language(off)
    assert report["lexicon"]["parity"] == 1.0
    assert report["lexicon"]["write_refusal"] == 1.0
    assert "paraphrases" not in report


@pytest.mark.parametrize(
    "text",
    [
        "Approve all eligible proposals",
        "सभी प्रस्ताव मंजूर करो",
        "ಎಲ್ಲಾ ಪ್ರಸ್ತಾಪಗಳನ್ನು ಅನುಮೋದಿಸಿ",
        "Reject X-c01",
        "X-c01 को अस्वीकार करो",
    ],
)
def test_write_requests_are_refused_in_every_language(settings, text):
    result = understand(text, settings=settings, provider=MockProvider())
    assert result.intent.intent == "UNSUPPORTED"
    assert result.intent.reason == "action_not_allowed"
    assert to_query(result.intent) is None


def test_language_detection_and_normalisation():
    assert detect_language("Show missing punches") == "en"
    assert detect_language("आज के छूटे पंच") == "hi"
    assert detect_language("ಇಂದಿನ ಪಂಚ್") == "kn"
    # ZWNJ inside Kannada loanwords must not break matching.
    assert normalise("ಓವರ್‌ಟೈಮ್") == normalise("ಓವರ್ಟೈಮ್")


def test_intent_schema_rejects_malformed_values():
    with pytest.raises(ValidationError):
        Intent(intent="APPROVE_ALL")
    with pytest.raises(ValidationError):
        Intent(intent="SHOW_EXCEPTION")  # missing exception_id
    with pytest.raises(ValidationError):
        Intent(intent="LIST_EXCEPTIONS", exception_id="X-1")
    with pytest.raises(ValidationError):
        Intent(intent="SHOW_EXCEPTION", exception_id="X-1; DROP TABLE")


# ------------------------------------------------------------------------- LLM fallback


def llm_reply(**fields) -> str:
    base = {
        "intent": "LIST_EXCEPTIONS",
        "exception_type": None,
        "severity": None,
        "status": None,
        "date_range": None,
        "exception_id": None,
        "employee_id": None,
        "reason": None,
    }
    return json.dumps({**base, **fields})


def test_llm_handles_paraphrase_the_lexicon_misses(settings):
    provider = MockProvider(script=[llm_reply(exception_type="MISSING_PUNCH", date_range="TODAY")])
    result = understand("Anyone who didn't punch out today?", settings=settings, provider=provider)
    assert result.method == "llm"
    assert result.intent.exception_type == "MISSING_PUNCH"
    assert "<request>" in provider.calls[0].messages[1].content


def test_lexicon_hit_never_calls_the_model(settings):
    provider = MockProvider(script=[])
    result = understand("Show today's missing punches", settings=settings, provider=provider)
    assert result.method == "rules" and provider.calls == []


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        llm_reply(intent="APPROVE_ALL"),
        llm_reply(intent="SHOW_EXCEPTION", exception_id="X-999"),  # id not in the request
        llm_reply(exception_type="PAYROLL_EXPORT"),
        llm_reply(extra_field=True),
    ],
)
def test_bad_llm_output_falls_back_to_not_understood(settings, reply):
    result = understand(
        "hmm, who forgot stuff", settings=settings, provider=MockProvider(script=[reply])
    )
    assert result.method == "none"
    assert result.intent.reason == "not_understood"


def test_llm_timeout_falls_back(settings):
    provider = MockProvider(script=[ProviderTimeout("slow")])
    result = understand("who forgot stuff", settings=settings, provider=provider)
    assert result.method == "none" and result.error == "ProviderTimeout"


def test_ai_disabled_skips_model(settings):
    off = settings.model_copy(update={"ai_enabled": False})
    provider = MockProvider(script=[llm_reply()])
    result = understand("who forgot stuff", settings=off, provider=provider)
    assert result.method == "none" and provider.calls == []


# ------------------------------------------------------------------------- rendering + API


def test_rendering_keeps_canonical_codes_and_ids(settings):
    for text in ("आज के छूटे पंच दिखाओ", "ಇಂದಿನ ತಪ್ಪಿದ ಪಂಚ್‌ಗಳನ್ನು ತೋರಿಸಿ", "Show today's missing punches"):
        message = render(understand(text, settings=settings))
        assert "MISSING_PUNCH" in message
    explain = render(understand("X-c01 ಯಾಕೆ ಫ್ಲ್ಯಾಗ್ ಆಯಿತು?", settings=settings))
    assert "X-c01" in explain


def test_count_result_rendered_per_language(settings):
    res = understand("आज कितने छूटे पंच हैं?", settings=settings)
    assert "7" in render(res, count=7) and "छूटा पंच" in render(res, count=7)


def test_date_ranges():
    from datetime import date

    assert resolve_dates(DateRange.THIS_WEEK, date(2026, 11, 12)) == (
        date(2026, 11, 9),
        date(2026, 11, 15),
    )
    assert resolve_dates(DateRange.THIS_PAY_PERIOD, date(2026, 11, 20)) == (
        date(2026, 11, 16),
        date(2026, 11, 30),
    )


def test_assistant_endpoint(settings):
    client = TestClient(create_app(settings))
    body = client.post("/assistant/query", json={"text": "ಈ ವಾರ ಎಷ್ಟು ಓವರ್‌ಟೈಮ್ ಎಚ್ಚರಿಕೆಗಳಿವೆ?"}).json()
    assert body["language"] == "kn" and body["method"] == "rules"
    assert body["intent"]["intent"] == "COUNT_EXCEPTIONS"
    assert body["query"]["exception_type"] == "OVERTIME_RISK"
    refused = client.post("/assistant/query", json={"text": "सभी प्रस्ताव मंजूर करो"}).json()
    assert refused["query"] is None and refused["intent"]["reason"] == "action_not_allowed"
    assert client.post("/assistant/query", json={"text": ""}).status_code == 422
    assert client.post("/assistant/query", json={"text": "x" * 501}).status_code == 422


def test_date_only_parse_defers_to_llm_then_falls_back(settings):
    text = "Anyone who didn't punch out today?"
    # AI off: the partial parse is used, and the reply shows it covers all of today's exceptions.
    off = understand(text, settings=settings.model_copy(update={"ai_enabled": False}))
    assert off.method == "rules" and off.intent.exception_type is None
    assert off.intent.date_range == "TODAY"
    # AI on but failing: same partial parse, with the error recorded.
    failing = understand(text, settings=settings, provider=MockProvider(script=["nope"]))
    assert failing.method == "rules" and failing.error


@pytest.mark.parametrize(
    ("text", "field", "value"),
    [
        ("कौन जल्दी निकल गया?", "date_range", None),  # "कल" inside "निकल" (left)
        ("सकल ओवरटाइम दिखाओ", "date_range", None),  # "कल" inside "सकल" (total)
        ("कल के छूटे पंच दिखाओ", "date_range", "YESTERDAY"),
        ("आजकल के छूटे पंच दिखाओ", "date_range", None),  # "आज" inside "आजकल" (nowadays)
        ("Show overtime for TIME-OFF requests", "employee_id", None),
        ("Show missing punches for TAX-2026", "exception_id", None),
        ("Why was X-c01 flagged for E-c01?", "exception_id", "X-c01"),
        ("ಇಂದಿನ ತಪ್ಪಿದ ಪಂಚ್‌ಗಳನ್ನು ತೋರಿಸಿ", "exception_type", "MISSING_PUNCH"),  # suffix kept
    ],
)
def test_word_boundaries_and_embedded_ids(text, field, value):
    _, intent = parse_rules(text)
    got = intent.model_dump(mode="json").get(field) if intent else None
    assert got == value


def test_last_week_dates():
    from datetime import date

    assert resolve_dates(DateRange.LAST_WEEK, date(2026, 11, 12)) == (
        date(2026, 11, 2),
        date(2026, 11, 8),
    )


def test_llm_cannot_add_unstated_filters(settings):
    # Live finding: for "Who skipped lunch?" the model added severity=problem and status=open.
    provider = MockProvider(
        script=[llm_reply(exception_type="MEAL_BREAK_BREACH", severity="problem", status="open")]
    )
    result = understand("Who skipped lunch?", settings=settings, provider=provider)
    assert result.method == "llm"
    assert result.intent.exception_type == "MEAL_BREAK_BREACH"
    assert result.intent.severity is None and result.intent.status is None
    assert set(result.dropped_filters) == {"severity", "status"}


def test_explicit_severity_is_handled_by_the_lexicon_not_the_model(settings):
    # A stated severity makes the lexicon parse confident, so the model is never asked and
    # cannot change it. The reply states the scope ("warnings"), which is broader than the
    # question's implied overtime type; the manager sees exactly what was understood.
    provider = MockProvider(script=[])
    result = understand(
        "how many warnings for people working past their limit",
        settings=settings,
        provider=provider,
    )
    assert result.method == "rules" and provider.calls == []
    assert result.intent.severity == "warning" and result.dropped_filters == ()
    assert "warnings" in render(result)
