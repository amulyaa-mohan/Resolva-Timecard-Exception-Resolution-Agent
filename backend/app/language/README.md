# Language

Track B (B-04): multilingual manager requests to allow-listed, language-neutral intents.

- `intents.py`: `Intent` schema (LIST/COUNT/SHOW/EXPLAIN, or UNSUPPORTED), script-based language
  detection (English, Hindi, Kannada), and the deterministic lexicon parser. The parser reports
  whether a parse is confident (it recognised a type, id, severity, status or write verb).
- `assistant.py`: `understand()` = lexicon first, then the LLM fallback (`prompts/intent_v1.md`,
  JSON mode, schema-validated, ids must appear verbatim in the request), then a partial lexicon
  parse or "not understood". `render()` produces fixed localized replies; ids, exception codes and
  policy citations stay canonical. `to_query()` gives the filters for Track A's exception list.
- `router.py`: `POST /assistant/query {"text": ...}`.

The model may interpret meaning (exception type, date range) but may not add explicit filters
(severity, status, employee) that the request does not state; those come from the lexicon only.

The layer is read-only. Requests to approve, reject, edit, delete or add are refused in every
language; decisions happen only in the authorised manager workflow.

Lexicons cover a tested demo command set and need review by native Hindi and Kannada speakers
before real use. A well-formed but wrong LLM intent cannot be detected by the schema; the reply
always states what was understood, so the manager can see a mismatch, and nothing is changed.
