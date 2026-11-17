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
from pathlib import Path

from pydantic import ValidationError

from app.ai.providers.base import (
    ChatMessage,
    LLMProvider,
    ProviderError,
    ProviderRequest,
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
    ValidationResult,
)
from app.core.tracing import get_trace_id
from app.retrieval.keyword import RetrievedClause, retrieve

PROMPT_VERSION = "propose_v1"


# ---------------------------------------------------------------------------- prompt


def _escape_untrusted(text: str) -> str:
    """Stop note text from closing its own tag or opening new sections."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_messages(
    case: CaseContext, retrieved: list[RetrievedClause], prompts_dir: Path
) -> tuple[ChatMessage, ...]:
    template = (prompts_dir / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    allowed = ", ".join(sorted(a.value for a in ALLOWED_ACTIONS[case.code]))
    system = template.format(allowed_actions=allowed)

    case_data = case.model_dump(mode="json", exclude={"notes"})
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
    user = (
        f"<case_json>{json.dumps(case_data, sort_keys=True)}</case_json>\n"
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
                prompt_version=PROMPT_VERSION,
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
) -> ProposalResult:
    """Contract function generate_proposal(case_context, policy_snapshot) -> ProposalResult."""
    run = _Run(case, policy, provider)

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

    # Gate 2: retrieval must find supporting clauses in the applicable version only.
    retrieved = retrieve(case, policy, top_k=settings.retrieval_top_k)
    run.retrieved_ids = [r.clause.chunk_id for r in retrieved]
    if not run.check("policy_evidence", bool(retrieved), f"{len(retrieved)} clause(s)"):
        return run.finish(GateStatus.ESCALATED, ["No supporting policy clause was retrieved."])
    clauses_by_id = {r.clause.chunk_id: r.clause for r in retrieved}

    # Generation with one repair retry on malformed output.
    messages = build_messages(case, retrieved, settings.prompts_dir)
    run.prompt_hash = prompt_hash(messages)
    proposal: LLMProposal | None = None
    for _ in range(1 + settings.llm_max_repair_retries):
        run.attempts += 1
        request = ProviderRequest(
            messages=messages,
            temperature=settings.llm_temperature,
            timeout_s=settings.llm_timeout_s,
        )
        try:
            response = provider.complete(request)
        except ProviderTimeout as exc:
            run.error = f"timeout: {exc}"
            run.check("provider", False, "timeout")
            return run.finish(GateStatus.ESCALATED, ["AI timed out; manual review (rules-only)."])
        except ProviderError as exc:
            run.error = f"provider_error: {exc}"
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

    if proposal.decision == "escalate":
        if blocked:
            return run.finish(GateStatus.BLOCKED, blocked, proposal)
        reasons = proposal.missing_information or ["The AI declined to propose a correction."]
        return run.finish(GateStatus.ESCALATED, reasons, proposal)

    # Deterministic evidence gates on a "propose" decision.
    allowed = ALLOWED_ACTIONS[case.code]
    bad_actions = sorted({a.type.value for a in proposal.actions if a.type not in allowed})
    if not run.check("actions_allowed", not bad_actions, ", ".join(bad_actions)):
        blocked.append(f"Action(s) not allowed for {case.code.value}: {', '.join(bad_actions)}.")

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
    validation: ValidationResult | None = None
    if not blocked:
        try:
            validation = validator(case, list(proposal.actions), policy)
        except Exception as exc:  # validator failure must never let a proposal through
            run.check("rules_revalidation", False, f"validator error: {type(exc).__name__}")
            blocked.append("Rule re-validation failed to run.")
        else:
            failed = [f"{c.code.value}: {c.reason}" for c in validation.checks if not c.passed]
            if not run.check("rules_revalidation", validation.passed, "; ".join(failed)):
                blocked.append("Proposed correction fails rule validation: " + "; ".join(failed))
    if blocked:
        return run.finish(GateStatus.BLOCKED, blocked, proposal, validation)

    escalate: list[str] = []
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
