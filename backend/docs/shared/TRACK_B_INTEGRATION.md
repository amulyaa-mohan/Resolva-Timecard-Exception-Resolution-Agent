# Track A ↔ Track B integration guide

Audience: C V Jayanth (Track A) and his coding agent (Codex). Maintained by Amulya Mohan (Track B).
Purpose: show exactly what Track B already provides, what Track A must supply, and how the two
connect, so Track A can build against real code instead of guessing.
Last updated: 2026-11-17 (B-03). Contract version: `0.1.0-draft` (not frozen; see "Decisions for SHARED-01").

## 1. What already exists and runs

All paths are relative to the repository root. Everything listed was run and tested on `backend`.

| Path | What it does | Owner |
| --- | --- | --- |
| `backend/app/core/contracts.py` | **Draft SHARED-01 contracts**: every type that crosses the A/B boundary | Shared (review needed) |
| `backend/app/core/config.py` | Settings from env or `backend/.env`: your `app_name`/`cors_origins` + AI settings and kill-switch | Shared |
| `backend/app/core/errors.py` | RFC 7807 `application/problem+json` for every error, with `trace_id` | Shared (proposal) |
| `backend/app/core/tracing.py` | `X-Trace-Id` per request; `get_trace_id()` for logs and audit events | Shared (proposal) |
| `backend/app/policies/registry.py` | Loads versioned packs; `resolve_policy(employee, work_date, registry)` | B |
| `backend/policies/IN-KA/2025.1.*` | Karnataka pack (active): thresholds + 11 citable clauses (`IN-KA@2025.1#KA-8`) | B |
| `backend/policies/IN-KA/2025.2-proposed.*` | Proposed amendment (status `proposed`, never resolved); wrong-version tests | B |
| `backend/policies/US-FED/2025.1.*` | US federal + California overlay pack: 8 h daily / 40 h weekly OT, 30 min meal | B |
| `backend/app/retrieval/hybrid.py` | Hybrid retrieval: pack/version filter, BM25 + vector, rank fusion (ADR-006) | B |
| `backend/app/ai/providers/` | `LLMProvider` interface: `MockProvider` (offline), `OllamaProvider`, `GroqProvider` | B |
| `backend/app/ai/pipeline.py` | `generate_proposal(...)`: prompt, parse, evidence gates, **calls your validator** | B |
| `backend/app/ai/evidence.py` | Pre-model evidence gate: escalates without calling the model when a fix cannot be justified | B |
| `backend/prompts/propose_v1.md` | Versioned system prompt | B |
| `backend/tests/factories.py` | `make_case()`, `passing_validator`, `failing_validator` test builders | Shared |
| `backend/Dockerfile`, `backend/docker-compose*.yml` | Backend container; optional `ollama` profile and GPU override | B |
| `backend/scripts/live_check.py` | Six-case smoke check against a real model | B |

Running API today: `GET /health` (now also reports `ai_enabled`, `llm_status`, `mode`) and `/docs`.
No exception, proposal, decision or audit endpoints exist yet; those depend on Track A.

## 2. The five boundary functions

```text
build_case_context(exception_id) -> CaseContext                       A implements  (A-01/A-02)
resolve_policy(employee, work_date, registry) -> PolicySnapshot        B implemented
generate_proposal(case, policy, *, provider, validator, settings)
    -> ProposalResult                                                  B implemented
validate_correction(case, actions, policy) -> ValidationResult         A implements  (A-02)
record_audit(event) -> AuditEvent                                      A implements  (A-03)
```

### What Track A must supply

**`CaseContext`** (`contracts.py`). Fields you fill from your attendance data:

- `exception_id`, `code: ExceptionCode`, `severity: Severity` (`DEFAULT_SEVERITY` gives the doc's mapping).
- `employee: EmployeeContext` with `jurisdiction` (e.g. `"IN-KA"`; this selects the policy pack) and IANA `timezone`.
- `work_date`, `rule_version` (version string of your rule set).
- `punches` (raw punches for the work date), `punch_history` (previous 7 days), `schedule` (or `None`).
- `notes`: employee free text. Track B treats it as **untrusted**; it is escaped and wrapped, never obeyed.
- `detection_details`: flat dict of scalars your rule found (e.g. `{"unmatched_punch_id": "P-1"}`).
- `evidence_version`: an opaque hash of the evidence above. **You compute it.** Approval must reject a
  proposal whose `evidence_version` differs from a freshly built `CaseContext`.

All datetimes must be timezone-aware; naive datetimes fail validation. All models are frozen and reject unknown fields.

**`validate_correction`** must match the `CorrectionValidator` protocol:

```python
def validate_correction(
    case: CaseContext, actions: list[ProposedAction], policy: PolicySnapshot
) -> ValidationResult:
    """Apply actions to a copy of the timecard and re-run the SAME rule functions as detection."""
```

Return `ValidationResult(passed, checks=[RuleCheck(code, passed, reason), ...], rule_version)`.
**Return at least one `RuleCheck`.** A result with an empty `checks` list has validated nothing, so the pipeline blocks it even when `passed=True`.
Jurisdictions available now: `IN-KA` and `US-FED`. In US-FED, `max_spread_hours` and
`quarterly_ot_cap_hours` are `None`: skip those rules rather than treating `None` as zero.
Read thresholds from `policy.rules` (`PolicyRules`: `daily_regular_hours`, `weekly_regular_hours`,
`max_spread_hours`, `overtime_rate`, `quarterly_ot_cap_hours`, `rest_after_hours`, `rest_minutes`,
`late_tolerance_min`, `missing_punch_window_min`). Never read thresholds from retrieved policy text.
If the validator raises, the pipeline blocks the proposal, so a crash can never approve anything.
Manager edits should call the same function (TEAM_RULES invariant).

### What Track B gives back

`ProposalResult.status` is one of three values. Treat them as follows:

| Status | Meaning | Track A should |
| --- | --- | --- |
| `eligible` | Every gate passed, including your validator | Show for approval; allow bulk approve |
| `blocked` | Model proposed, but a deterministic check failed (`reasons` says which) | Manual review only; never bulk approve |
| `escalated` | No safe proposal: missing evidence, refusal, low confidence, AI off, timeout | Manual review; show `reasons` as "what is missing" |

`ProposalResult` also carries `policy_pack_id`, `policy_version`, `evidence_version`, every `gate_checks`
entry, and `trace` (`LLMTrace`: model id, prompt version and hash, retrieved chunk ids, raw outputs,
parse errors, attempts, latency). Record these in the audit trail; they are the design doc's "model
version" and "prompt hash" audit fields.

**At approval, always re-check** (`generate_proposal` is not enough on its own):
1. Server-side permission for this manager and employee.
2. `evidence_version` still matches a freshly built `CaseContext`.
3. `validate_correction` passes again against current evidence.
4. The proposal has not already been decided (idempotency).

### Evidence gate before the model (B-03)

Some cases escalate without calling the model at all (`gate_checks` entry `evidence_sufficient`).
Today: `MISSING_PUNCH` with no `schedule` and no same-weekday punch in `punch_history`. The live
Qwen2.5-7B check showed why: with no schedule the model invented a clock-out 30 minutes after
clock-in, and no attendance rule flags such a shift. Fill `punch_history` (previous 7 days) so
this gate can use it.

The design doc's other "always escalate" cases need agreed `detection_details` keys. Proposed:
`overlap_minutes` (OVERLAPPING_SHIFT; escalate above 120), `spread_minutes` (SPREAD_OVER_BREACH),
`quarter_ot_hours` (OVERTIME_RISK). Confirm or rename them as part of SHARED-01 decision 11.

## 3. Wiring example (for your resolution module)

```python
from app.ai.pipeline import generate_proposal
from app.ai.providers import build_provider
from app.core.config import get_settings
from app.policies.registry import PolicyRegistry, PolicyResolutionError, resolve_policy

settings = get_settings()
registry = PolicyRegistry.from_directory(settings.policies_dir)  # build once at startup


def propose(exception_id: str):
    case = build_case_context(exception_id)  # Track A
    try:
        policy = resolve_policy(case.employee, case.work_date, registry)
    except PolicyResolutionError:
        policy = None  # pipeline escalates safely
    return generate_proposal(
        case,
        policy,
        provider=build_provider(settings),
        validator=validate_correction,  # Track A
        settings=settings,
    )
```

Suggested idempotency key for `POST /exceptions/{id}/propose`:
`(exception_id, evidence_version, policy.content_hash, trace.prompt_version)`.

## 4. Testing against Track B without waiting

```python
from tests.factories import make_case, passing_validator, failing_validator
```

- `make_case()` builds a synthetic missing-clock-out case (IN-KA, 09:02 IST clock-in, 09:00–18:00 schedule).
- Swap `passing_validator` for your real `validate_correction` to prove the pipeline path end to end.
- The pytest fixtures `settings`, `registry`, `policy`, `case` are in `backend/tests/conftest.py`.
- With the mock provider, a missing clock-out yields `eligible` with an `add_punch` out at 18:00 citing KA-8.
  Mock results prove the harness, not model quality.

## 5. Decisions for SHARED-01 (Jayanth to confirm or change)

There are 11 decisions. Reply in `backend/docs/UPDATE.md` or a PR comment. Until agreed, the contract stays `0.1.0-draft`.

1. **IDs** are opaque strings everywhere. OK?
2. **`work_date`** is the local date in `employee.timezone` of the shift start (overnight shifts belong to their start date). OK?
3. **`evidence_version`**: proposed as sha256 of canonical JSON of punches, schedule, notes and existing corrections. You own the exact recipe.
4. **Validator semantics**: `passed` is true only if the target exception is resolved **and** no new exception of any code appears. Should new warning-level exceptions also fail it?
5. **Action targets**: `void_shift`, `add_break` and `suggest_schedule_swap` have no target fields yet (shift id, break start/end). Propose fields with A-04, or now?
6. **Manual corrections** reuse `ProposedAction` as the action type, so one validator handles AI and manager edits. OK?
7. **`AuditEvent`** is Track A's contract and is not drafted yet. It needs `trace_id`, `model_id` and `prompt_hash` from `ProposalResult.trace`.
8. **Persistence**: Track B proposes `proposals` (from `ProposalResult`) and `llm_traces` (from `LLMTrace`) tables; you and the database team own migration ordering.
9. **Route ownership**: suggest Track A owns `/exceptions/*` and `/proposals/*` routes and calls `generate_proposal`. OK?
10. **Severity**: `DEFAULT_SEVERITY` follows design doc section 8. OK?
11. **`detection_details` keys** for the evidence gate: `overlap_minutes`, `spread_minutes`,
    `quarter_ot_hours` (see "Evidence gate before the model"). OK, or other names?

## 6. Rules for both agents

- Don't edit another track's modules: Track B owns `app/{policies,retrieval,ai,language}`, `policies/` and `prompts/`. Propose changes in `UPDATE.md` or a PR.
- Changes to `app/core/contracts.py` are shared: propose, get agreement, bump `CONTRACT_VERSION`.
- Never import from `app.ai` inside rules or the validator. Detection and validation stay deterministic.
- The LLM never writes data. Only Track A's decision path creates corrections, after manager approval.
- Work on `backend`; `git fetch` and integrate teammate work before pushing; never force-push.
- Log task status in `backend/docs/shared/TASKS.md` and append to `backend/docs/UPDATE.md`.

## 7. Checks

```bash
# macOS/Linux
.venv/bin/python -m pytest backend/tests
.venv/bin/python -m ruff check backend && .venv/bin/python -m ruff format --check backend
# Windows (Git Bash)
venv/Scripts/python.exe -m pytest backend/tests
```

## 8. Prompt to give Codex at the start of a Track A session

```text
I am C V Jayanth, backend track A, on branch backend.
Read AGENTS.md, backend/docs/AGENTS.md, backend/docs/shared/TASKS.md, the latest backend/docs/UPDATE.md
entries, and backend/docs/shared/TRACK_B_INTEGRATION.md before changing code.
Track B (Amulya) has implemented the policy registry, retrieval, provider interface and generate_proposal;
the shared contracts are a draft in backend/app/core/contracts.py.
Build Track A against those contracts: CaseContext, validate_correction matching CorrectionValidator,
and ValidationResult. Do not edit Track B modules or contracts.py without a written proposal.
Reuse backend/tests/factories.py in tests. Run pytest and ruff, update TASKS.md and UPDATE.md.
Do not commit or push unless I authorize it.
```
