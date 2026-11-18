-- Proposal persistence, model traces and escalation state (Track A, 2026-11-18).
-- JSON payloads are canonical JSON text, not jsonb, so one code path serves both the
-- PostgreSQL store and the demo SQLite store. Query them in the application, not in SQL.

CREATE TABLE proposals (
    proposal_id      text PRIMARY KEY,
    exception_id     text NOT NULL REFERENCES exceptions ON DELETE RESTRICT,
    requested_by     text NOT NULL REFERENCES managers ON DELETE RESTRICT,
    status           text NOT NULL CHECK (status IN ('eligible', 'blocked', 'escalated')),
    evidence_version text NOT NULL,
    policy_pack_id   text,
    policy_version   text,
    rule_version     text,
    proposal_json    text,                     -- LLMProposal, null when the model produced none
    validation_json  text,                     -- ValidationResult, null when never validated
    gate_checks_json text NOT NULL,
    reasons_json     text NOT NULL,
    created_at       timestamptz NOT NULL
);
CREATE INDEX proposals_exception ON proposals (exception_id, created_at);

-- Model call provenance. raw_outputs holds model text: it is evidence for an audit, so it
-- is kept with the proposal and removed only by a retention job agreed with Track B.
CREATE TABLE llm_traces (
    trace_id            text PRIMARY KEY,
    proposal_id         text NOT NULL REFERENCES proposals ON DELETE RESTRICT,
    provider            text NOT NULL,
    model_id            text,
    prompt_version      text NOT NULL,
    prompt_hash         text,
    retrieved_chunk_ids text NOT NULL,
    raw_outputs         text NOT NULL,
    parse_errors        text NOT NULL,
    attempts            integer NOT NULL,
    latency_ms          integer NOT NULL,
    error               text,
    created_at          timestamptz NOT NULL
);

-- An exception referred to a human instead of being approved. First escalation wins;
-- an approval later supersedes it (status is derived: resolved > escalated > open).
CREATE TABLE escalations (
    exception_id text PRIMARY KEY REFERENCES exceptions ON DELETE RESTRICT,
    reason       text NOT NULL,
    source       text NOT NULL CHECK (source IN ('pipeline', 'manager')),
    escalated_at timestamptz NOT NULL
);

CREATE TRIGGER proposals_append_only BEFORE UPDATE OR DELETE ON proposals
    FOR EACH ROW EXECUTE FUNCTION resolva_append_only();
CREATE TRIGGER llm_traces_append_only BEFORE UPDATE OR DELETE ON llm_traces
    FOR EACH ROW EXECUTE FUNCTION resolva_append_only();

-- A manager may also refer a case upward without approving or rejecting it.
ALTER TABLE decisions DROP CONSTRAINT decisions_decision_check;
ALTER TABLE decisions ADD CONSTRAINT decisions_decision_check
    CHECK (decision IN ('approve', 'reject', 'escalate'));
