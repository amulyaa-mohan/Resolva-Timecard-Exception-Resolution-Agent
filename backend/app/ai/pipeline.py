"""Proposal pipeline (B-02): retrieve -> prompt -> LLM -> schema -> evidence gates -> validator.

The result is always one of: an ELIGIBLE validated, cited proposal; a BLOCKED proposal that
failed a deterministic check; or an ESCALATED case that says what is missing. Model
confidence is logged and gated, but it can never override a failed check.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from app.ai.evidence import (
    STATED_TIME_CODES,
    WORK_PUNCHES,
    anchor_times,
    local_zone,
    missing_evidence,
    stated_times,
)
from app.ai.providers.base import (
    ChatMessage,
    LLMProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeout,
)
from app.core.config import Settings
from app.core.contracts import (
    ALLOWED_ACTIONS,
    CaseContext,
    CorrectionValidator,
    GateCheck,
    GateStatus,
    LLMProposal,
    LLMTrace,
    PolicySnapshot,
    ProposalResult,
    RuleOutcome,
    ValidationResult,
)
from app.core.tracing import get_trace_id
from app.retrieval.hybrid import RetrievedClause, retrieve
from app.retrieval.vector import Embedder, build_embedder

# v1: case JSON + clauses. v2 adds a trusted <facts> block (local times with dates); see evals.
DEFAULT_PROMPT_VERSION = "propose_v3"


# ---------------------------------------------------------------------------- prompt


def _escape_untrusted(text: str) -> str:
    """Stop note text from closing its own tag or opening new sections."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def case_facts(case: CaseContext, policy: PolicySnapshot | None) -> str:
    """Trusted, deterministic plain-language facts (prompt v2).

    The v1 eval showed the model mishandling dates across midnight (a 22:00-06:00 shift got a
    same-day 23:37 clock-out). Stating local times with dates removes that arithmetic.
    """

    zone = local_zone(case)  # stored timestamps may be UTC; the model reasons in local time

    def local(ts) -> str:
        return ts.astimezone(zone).strftime("%a %Y-%m-%d %H:%M (UTC%z)")

    lines = [f"Work date: {case.work_date.isoformat()} ({case.work_date:%A})"]
    if case.as_of is not None:
        lines.append(f"Evaluation time (now): {local(case.as_of)}")
    if case.schedule:
        lines.append(f"Scheduled shift: {local(case.schedule.start)} to {local(case.schedule.end)}")
    else:
        lines.append("Scheduled shift: none")
    for p in case.punches:
        lines.append(f"Recorded punch {p.punch_id}: {p.type.value} at {local(p.ts)}")
    if case.code.value == "MISSING_PUNCH":
        ins = sum(p.type.value == "in" for p in case.punches)
        outs = sum(p.type.value == "out" for p in case.punches)
        if ins > outs:
            lines.append("Missing punch type: out (clock-out)")
            if case.schedule:
                lines.append(f"Scheduled clock-out to infer from: {local(case.schedule.end)}")
        elif outs > ins:
            lines.append("Missing punch type: in (clock-in)")
            if case.schedule:
                lines.append(f"Scheduled clock-in to infer from: {local(case.schedule.start)}")
        else:
            lines.append("Missing punch type: unclear (punches already pair up)")
    if policy is not None and case.code.value == "MISSING_PUNCH":
        lines.append(
            f"Inference window: within {policy.rules.missing_punch_window_min} minutes of the "
            "scheduled time"
        )
    if case.code in STATED_TIME_CODES:
        lines += _adjustment_facts(case, policy, local)
    return "\n".join(lines)


def _minutes(delta) -> int:
    return round(delta.total_seconds() / 60)


def _adjustment_facts(case: CaseContext, policy: PolicySnapshot | None, local) -> list[str]:
    """Facts for codes fixed only by moving a recorded punch to a stated time (step 2)."""
    lines = []
    stated = stated_times(case)
    lines.append(
        "Times stated in employee notes (claims, not proof): "
        + (", ".join(f"{h:02d}:{m:02d} (note {nid})" for nid, h, m in stated) or "none")
    )
    work = sorted((p for p in case.punches if p.type in WORK_PUNCHES), key=lambda p: p.ts)
    ins = [p for p in work if p.type.value == "in"]
    outs = [p for p in work if p.type.value == "out"]
    tolerance = policy.rules.late_tolerance_min if policy else None
    if case.code.value == "SCHEDULE_DEVIATION" and case.schedule:
        if ins:
            late = _minutes(ins[0].ts - case.schedule.start)
            lines.append(
                f"First clock-in {ins[0].punch_id} is {abs(late)} min "
                f"{'after' if late >= 0 else 'before'} the scheduled start"
                + (f" (tolerance {tolerance} min)" if tolerance is not None else "")
            )
        if outs:
            off = _minutes(outs[-1].ts - case.schedule.end)
            lines.append(
                f"Last clock-out {outs[-1].punch_id} is {abs(off)} min "
                f"{'after' if off >= 0 else 'before'} the scheduled end"
            )
    if case.code.value == "SPREAD_OVER_BREACH" and ins and outs:
        spread = _minutes(outs[-1].ts - ins[0].ts)
        limit = policy.rules.max_spread_hours if policy else None
        lines.append(
            f"Spread from first clock-in {ins[0].punch_id} to last clock-out {outs[-1].punch_id}: "
            f"{spread // 60} h {spread % 60} min" + (f" (limit {limit:g} h)" if limit else "")
        )
    if case.code.value == "OVERLAPPING_SHIFT":
        # FIFO pairing, as Track A's engine pairs work punches.
        sessions, pending = [], []
        for p in work:
            if p.type.value == "in":
                pending.append(p)
            elif pending:
                sessions.append((pending.pop(0), p))
        for i, (a_in, a_out) in enumerate(sessions):
            for b_in, b_out in sessions[i + 1 :]:
                overlap = _minutes(min(a_out.ts, b_out.ts) - max(a_in.ts, b_in.ts))
                if overlap > 0:
                    lines.append(
                        f"Session {a_in.punch_id}-{a_out.punch_id} overlaps session "
                        f"{b_in.punch_id}-{b_out.punch_id} by {overlap} min"
                    )
    if policy is not None:
        lines.append(
            "Allowed fix: adjust_punch on one recorded punch (punch_id) to a time the employee "
            f"stated, moving it at most {policy.rules.missing_punch_window_min} min. Round only so "
            "no paid time is added: a clock-in at or after the stated time, a clock-out at or "
            f"before it, within {policy.rules.evidence_tolerance_min} min. Never move a punch to "
            "the scheduled time unless the employee stated that time. If no stated time describes "
            "a punching error, escalate."
        )
    return lines


def _localised(case: CaseContext) -> CaseContext:
    """The case with every timestamp in the employee's local time zone.

    Found in the live demo on PostgreSQL (2026-11-18): the database returns UTC, so the model
    saw 09:25+00:00, copied that offset as instructed, and wrote the stated 09:05 as 09:05+00:00
    (14:35 local), which the time-evidence gate rightly refused. Same instants, local offsets.
    """
    zone = local_zone(case)

    def local(ts):
        return ts.astimezone(zone) if ts is not None else None

    def punches(items):
        return [p.model_copy(update={"ts": local(p.ts)}) for p in items]

    update = {
        "punches": punches(case.punches),
        "punch_history": punches(case.punch_history),
        "as_of": local(case.as_of),
    }
    if case.schedule is not None:
        update["schedule"] = case.schedule.model_copy(
            update={"start": local(case.schedule.start), "end": local(case.schedule.end)}
        )
    return case.model_copy(update=update)


def build_messages(
    case: CaseContext,
    retrieved: list[RetrievedClause],
    prompts_dir: Path,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    policy: PolicySnapshot | None = None,
) -> tuple[ChatMessage, ...]:
    template = (prompts_dir / f"{prompt_version}.md").read_text(encoding="utf-8")
    allowed = ", ".join(sorted(a.value for a in ALLOWED_ACTIONS[case.code]))
    system = template.format(allowed_actions=allowed)

    case_data = _localised(case).model_dump(mode="json", exclude={"notes"})
    clauses = [
        {
            "chunk_id": r.clause.chunk_id,
            "clause_id": r.clause.clause_id,
            "title": r.clause.title,
            "text": r.clause.text,
        }
        for r in retrieved
    ]
    notes = "\n".join(
        f'<untrusted_note id="{_escape_untrusted(n.note_id)}">{_escape_untrusted(n.text)}'
        "</untrusted_note>"
        for n in case.notes
    )
    facts = (
        f"<facts>\n{case_facts(case, policy)}\n</facts>\n" if prompt_version != "propose_v1" else ""
    )
    user = (
        facts + f"<case_json>{json.dumps(case_data, sort_keys=True)}</case_json>\n"
        f"<retrieved_clauses_json>{json.dumps(clauses)}</retrieved_clauses_json>\n"
        f"{notes or '<untrusted_note>(no employee note)</untrusted_note>'}\n"
        "Draft the correction or escalate. Reply with the JSON object only."
    )
    return (ChatMessage("system", system), ChatMessage("user", user))


def prompt_hash(messages: tuple[ChatMessage, ...]) -> str:
    joined = "\n\n".join(f"{m.role}:{m.content}" for m in messages)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


# A citation must quote enough of the clause to be checkable; "" or "the" proves nothing.
MIN_QUOTE_WORDS = 5
# Raw model output kept in the trace per attempt (full text is never needed for replay).
MAX_TRACE_OUTPUT_CHARS = 20_000

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(?P<body>.*)\n\s*```\s*$", re.DOTALL | re.IGNORECASE)


def _strip_code_fence(text: str) -> str:
    """Accept one JSON object wrapped in a Markdown code fence; the schema check still applies."""
    match = _FENCE.match(text)
    return match["body"] if match else text


def _quote_is_verbatim(quote: str, clause_text: str) -> bool:
    normalised = _normalise(quote)
    return len(normalised.split()) >= MIN_QUOTE_WORDS and normalised in _normalise(clause_text)


def canonical_citation_ids(
    proposal: LLMProposal, clauses_by_id: dict, policy: PolicySnapshot
) -> tuple[LLMProposal, list[str]]:
    """Repair a mangled chunk_id that unambiguously names a retrieved, active-version clause.

    Found in the step 2 live eval: Qwen2.5-7B cited KA-11 as "IN-KA@2025.1#KA-2025.1#KA-11" in 9 of
    10 runs while its decision and verbatim quote were right. Repair only when the id starts with
    the active "<pack>@<version>#" and its last "#" segment is the clause id of exactly one
    retrieved clause. Anything else (unknown clause, proposed version, other pack) is left as
    cited, so the citation gates still block it; the quote must still be verbatim from the clause.
    """
    prefix = f"{policy.pack_id}@{policy.version}#"
    repaired: list[str] = []
    citations = []
    for c in proposal.citations:
        if c.chunk_id not in clauses_by_id and c.chunk_id.startswith(prefix):
            tail = c.chunk_id.rsplit("#", 1)[-1]
            matches = [cid for cid, clause in clauses_by_id.items() if clause.clause_id == tail]
            if len(matches) == 1:
                repaired.append(f"{c.chunk_id} -> {matches[0]}")
                c = c.model_copy(update={"chunk_id": matches[0]})
        citations.append(c)
    if repaired:
        proposal = proposal.model_copy(update={"citations": citations})
    return proposal, repaired


def call_with_deadline(provider: LLMProvider, request: ProviderRequest) -> ProviderResponse:
    """Enforce a hard wall-clock budget on any provider.

    HTTP timeouts bound each network phase, not the whole call, so a slow-streaming server could
    exceed the budget. The worker thread is abandoned on timeout; its own HTTP timeout ends it.
    """
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-call")
    future = executor.submit(provider.complete, request)
    try:
        return future.result(timeout=request.timeout_s)
    except FutureTimeout as exc:
        raise ProviderTimeout(f"no response within {request.timeout_s:g}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------- pipeline


class _Run:
    """Accumulates trace data for one pipeline invocation."""

    def __init__(self, case: CaseContext, policy: PolicySnapshot | None, provider: LLMProvider):
        self.case, self.policy, self.provider = case, policy, provider
        self.started = time.perf_counter()
        self.checks: list[GateCheck] = []
        self.raw_outputs: list[str] = []
        self.parse_errors: list[str] = []
        self.retrieved_ids: list[str] = []
        self.prompt_hash: str | None = None
        self.model_id: str | None = None
        self.attempts = 0
        self.prompt_version = DEFAULT_PROMPT_VERSION
        self.error: str | None = None

    def check(self, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append(GateCheck(name=name, passed=passed, detail=detail))
        return passed

    def finish(
        self,
        status: GateStatus,
        reasons: list[str],
        proposal: LLMProposal | None = None,
        validation: ValidationResult | None = None,
    ) -> ProposalResult:
        return ProposalResult(
            exception_id=self.case.exception_id,
            status=status,
            proposal=proposal,
            validation=validation,
            gate_checks=self.checks,
            reasons=reasons,
            policy_pack_id=self.policy.pack_id if self.policy else None,
            policy_version=self.policy.version if self.policy else None,
            evidence_version=self.case.evidence_version,
            trace=LLMTrace(
                trace_id=get_trace_id(),
                provider=getattr(self.provider, "name", "unknown"),
                model_id=self.model_id,
                prompt_version=self.prompt_version,
                prompt_hash=self.prompt_hash,
                retrieved_chunk_ids=self.retrieved_ids,
                raw_outputs=self.raw_outputs,
                parse_errors=self.parse_errors,
                attempts=self.attempts,
                latency_ms=int((time.perf_counter() - self.started) * 1000),
                error=self.error,
            ),
        )


def generate_proposal(
    case: CaseContext,
    policy: PolicySnapshot | None,
    *,
    provider: LLMProvider,
    validator: CorrectionValidator,
    settings: Settings,
    embedder: Embedder | None = None,
) -> ProposalResult:
    """Contract function generate_proposal(case_context, policy_snapshot) -> ProposalResult."""
    run = _Run(case, policy, provider)
    run.prompt_version = settings.prompt_version

    # Gate 0: kill-switch. Detection and manual fixes keep working without AI.
    if not run.check("ai_enabled", settings.ai_enabled, "AI kill-switch"):
        return run.finish(GateStatus.ESCALATED, ["AI is disabled; manual review (rules-only)."])

    # Gate 1: an applicable policy must be resolved by trusted metadata.
    if policy is None:
        run.check("policy_resolved", False, "no applicable policy pack")
        return run.finish(GateStatus.ESCALATED, ["No applicable policy pack was resolved."])
    applicable = (
        policy.jurisdiction == case.employee.jurisdiction
        and policy.status == "active"
        and policy.effective_from <= case.work_date
        and (policy.effective_to is None or case.work_date < policy.effective_to)
    )
    if not run.check("policy_resolved", applicable, f"{policy.pack_id}@{policy.version}"):
        return run.finish(
            GateStatus.ESCALATED,
            [f"Policy {policy.pack_id}@{policy.version} does not apply to this case."],
        )

    # Gate 2: deterministic evidence sufficiency. If a fix cannot be justified, never ask the model.
    gaps = missing_evidence(case, policy)
    if not run.check("evidence_sufficient", not gaps, "; ".join(gaps)):
        return run.finish(GateStatus.ESCALATED, gaps)

    # Gate 3: retrieval must find supporting clauses in the applicable version only.
    retrieval = retrieve(
        case, policy, top_k=settings.retrieval_top_k, embedder=embedder or build_embedder(settings)
    )
    retrieved = retrieval.clauses
    run.check("retrieval_mode", True, retrieval.mode)
    run.retrieved_ids = [r.clause.chunk_id for r in retrieved]
    if not run.check("policy_evidence", bool(retrieved), f"{len(retrieved)} clause(s)"):
        return run.finish(GateStatus.ESCALATED, ["No supporting policy clause was retrieved."])
    clauses_by_id = {r.clause.chunk_id: r.clause for r in retrieved}

    # Generation with one repair retry on malformed output.
    messages = build_messages(
        case, retrieved, settings.prompts_dir, settings.prompt_version, policy
    )
    run.prompt_hash = prompt_hash(messages)
    proposal: LLMProposal | None = None
    # One budget for the whole generation, repair retry included (design target: p95 under 8 s).
    deadline = time.perf_counter() + settings.llm_timeout_s
    for _ in range(1 + settings.llm_max_repair_retries):
        remaining = deadline - time.perf_counter()
        request = ProviderRequest(
            messages=messages,
            temperature=settings.llm_temperature,
            timeout_s=max(remaining, 0.001),
        )
        try:
            if remaining <= 0:
                raise ProviderTimeout(f"budget of {settings.llm_timeout_s:g}s used up")
            run.attempts += 1
            response = call_with_deadline(provider, request)
        except ProviderTimeout as exc:
            run.error = f"timeout: {exc}"
            run.check("provider", False, "timeout")
            return run.finish(GateStatus.ESCALATED, ["AI timed out; manual review (rules-only)."])
        except Exception as exc:  # ProviderError or any adapter bug: fail safe to manual review
            run.error = f"provider_error: {type(exc).__name__}: {exc}"[:500]
            run.check("provider", False, "unavailable")
            return run.finish(GateStatus.ESCALATED, ["AI unavailable; manual review (rules-only)."])
        run.model_id = response.model_id
        run.raw_outputs.append(response.text[:MAX_TRACE_OUTPUT_CHARS])
        try:
            proposal = LLMProposal.model_validate_json(_strip_code_fence(response.text))
            break
        except ValidationError as exc:
            error = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}" for e in exc.errors()
            )
            run.parse_errors.append(error[:1000])
            messages = (
                *messages,
                ChatMessage("assistant", response.text[:4000]),
                ChatMessage(
                    "user",
                    f"Your reply did not match the required JSON schema: {error[:800]}. "
                    "Reply again with one corrected JSON object only.",
                ),
            )
    run.check("provider", True, run.model_id or "")
    if not run.check("schema", proposal is not None, f"{len(run.parse_errors)} parse error(s)"):
        return run.finish(GateStatus.ESCALATED, ["AI output was malformed after a repair retry."])
    assert proposal is not None

    blocked: list[str] = []
    if not run.check(
        "exception_match", proposal.exception_id == case.exception_id, proposal.exception_id
    ):
        blocked.append("Proposal refers to a different exception.")

    proposal, repaired = canonical_citation_ids(proposal, clauses_by_id, policy)
    if repaired:  # informational: the trace shows exactly what was normalised
        run.check("citation_ids_normalised", True, "; ".join(repaired))

    if proposal.decision == "escalate":
        # An escalation must never show fabricated citations (found in the live eval: an
        # injected note made the model cite a non-existent clause while escalating).
        verified = [
            c
            for c in proposal.citations
            if c.chunk_id in clauses_by_id
            and _quote_is_verbatim(c.quote, clauses_by_id[c.chunk_id].text)
        ]
        removed = [c.chunk_id for c in proposal.citations if c not in verified]
        if not run.check("escalation_citations", not removed, ", ".join(removed)):
            proposal = proposal.model_copy(update={"citations": verified})
        if blocked:
            return run.finish(GateStatus.BLOCKED, blocked, proposal)
        reasons = proposal.missing_information or ["The AI declined to propose a correction."]
        return run.finish(GateStatus.ESCALATED, reasons, proposal)

    # Deterministic evidence gates on a "propose" decision.
    allowed = ALLOWED_ACTIONS[case.code]
    bad_actions = sorted({a.type.value for a in proposal.actions if a.type not in allowed})
    if not run.check("actions_allowed", not bad_actions, ", ".join(bad_actions)):
        blocked.append(f"Action(s) not allowed for {case.code.value}: {', '.join(bad_actions)}.")

    tolerance = timedelta(minutes=policy.rules.evidence_tolerance_min)
    anchored, unanchored = anchor_times(case, list(proposal.actions), tolerance)
    if not run.check("time_evidence", not unanchored, "; ".join(unanchored)):
        blocked.append("Proposed time not supported by evidence: " + "; ".join(unanchored))
    else:
        # Every added time now names its evidence; the validator checks against the same ref.
        proposal = proposal.model_copy(update={"actions": anchored})

    unknown = [c.chunk_id for c in proposal.citations if c.chunk_id not in clauses_by_id]
    if not run.check("citations_retrieved", not unknown, ", ".join(unknown)):
        blocked.append(f"Citation(s) not in the retrieved policy evidence: {', '.join(unknown)}.")

    misquoted = [
        c.chunk_id
        for c in proposal.citations
        if c.chunk_id in clauses_by_id
        and not _quote_is_verbatim(c.quote, clauses_by_id[c.chunk_id].text)
    ]
    if not run.check("citation_quotes_verbatim", not misquoted, ", ".join(misquoted)):
        blocked.append(
            f"Quote is not a verbatim passage of at least {MIN_QUOTE_WORDS} words from the "
            f"cited clause: {', '.join(misquoted)}."
        )

    # Deterministic re-validation with Track A's rules (same functions as detection).
    # Contract 0.2.0: a violation blocks; insufficient evidence (and no violation) escalates.
    validation: ValidationResult | None = None
    undecided: list[str] = []
    if not blocked:
        try:
            validation = validator(case, list(proposal.actions), policy)
        except Exception as exc:  # validator failure must never let a proposal through
            run.check("rules_revalidation", False, f"validator error: {type(exc).__name__}")
            blocked.append("Rule re-validation failed to run.")
        else:

            def describe(outcome: RuleOutcome) -> list[str]:
                # Group identical reasons (audit 2026-11-18: an unsupported action repeated the
                # same sentence for all six rules).
                grouped: dict[str, list[str]] = {}
                for c in validation.checks:
                    if c.outcome == outcome:
                        grouped.setdefault(c.reason, []).append(c.code.value)
                return [f"{', '.join(codes)}: {reason}" for reason, codes in grouped.items()]

            violations = describe(RuleOutcome.VIOLATION)
            undecided = describe(RuleOutcome.INSUFFICIENT_EVIDENCE)
            if not validation.checks:
                # A result with no rule checks has validated nothing; it cannot approve.
                run.check("rules_revalidation", False, "validator returned no rule checks")
                blocked.append("Rule re-validation returned no checks.")
            elif not run.check("rules_revalidation", not violations, "; ".join(violations)):
                blocked.append(
                    "Proposed correction fails rule validation: " + "; ".join(violations)
                )
            elif not run.check(
                "rules_evidence", validation.passed and not undecided, "; ".join(undecided)
            ):
                # The contract makes passed=False with no violation mean 'undecided'.
                undecided = undecided or ["validator did not pass the correction"]
    if blocked:
        return run.finish(GateStatus.BLOCKED, blocked, proposal, validation)

    escalate: list[str] = []
    if undecided:
        escalate.append("Not enough evidence to validate the correction: " + "; ".join(undecided))
    if not run.check(
        "evidence_complete",
        not proposal.missing_information,
        "; ".join(proposal.missing_information),
    ):
        escalate.append("Missing information: " + "; ".join(proposal.missing_information))
    if not run.check(
        "confidence",
        proposal.confidence >= settings.confidence_threshold,
        f"{proposal.confidence:.2f} vs threshold {settings.confidence_threshold:.2f}",
    ):
        escalate.append("Model confidence below the configured threshold.")
    if escalate:
        return run.finish(GateStatus.ESCALATED, escalate, proposal, validation)

    return run.finish(GateStatus.ELIGIBLE, [], proposal, validation)
