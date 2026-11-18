"""Multilingual parity evaluation (B-04), used by evals/run.py.

Lexicon set (deterministic, gated in CI): every command must give the expected intent in English,
Hindi and Kannada, and all three must be identical. Paraphrase set (needs a model): requests the
lexicon does not cover, measured through the LLM fallback; reported, not gated.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.language.assistant import understand

EVALS_DIR = Path(__file__).resolve().parent
LANGS = ("en", "hi", "kn")


def _matches(intent, expected: dict) -> bool:
    got = intent.model_dump(mode="json", exclude_none=True)
    if expected.get("intent") == "UNSUPPORTED" and "reason" not in expected:
        return got["intent"] == "UNSUPPORTED"
    return got == expected


def _run_set(path: Path, settings, provider) -> dict:
    rows = []
    for item in json.loads(path.read_text("utf-8")):
        per_lang = {}
        for lang in LANGS:
            res = understand(item[lang], settings=settings, provider=provider)
            per_lang[lang] = {
                "text": item[lang],
                "detected": res.language,
                "method": res.method,
                "intent": res.intent.model_dump(mode="json", exclude_none=True),
                "ok": _matches(res.intent, item["expected"]) and res.language == lang,
            }
        intents = [json.dumps(v["intent"], sort_keys=True) for v in per_lang.values()]
        rows.append(
            {
                "id": item["id"],
                "expected": item["expected"],
                "results": per_lang,
                "parity": len(set(intents)) == 1 and all(v["ok"] for v in per_lang.values()),
            }
        )
    n = len(rows)
    return {
        "rows": rows,
        "accuracy_by_language": {
            lang: sum(r["results"][lang]["ok"] for r in rows) / n for lang in LANGS
        },
        "parity": sum(r["parity"] for r in rows) / n,
        "write_refusal": (
            sum(r["parity"] for r in rows if r["expected"].get("reason") == "action_not_allowed")
            / max(1, sum(r["expected"].get("reason") == "action_not_allowed" for r in rows))
        ),
    }


def eval_language(settings, provider=None) -> dict:
    rules_only = settings.model_copy(update={"ai_enabled": False})
    result = {"lexicon": _run_set(EVALS_DIR / "language_cases.json", rules_only, None)}
    if provider is not None and settings.ai_enabled:
        result["paraphrases"] = _run_set(
            EVALS_DIR / "language_paraphrases.json", settings, provider
        )
    return result
