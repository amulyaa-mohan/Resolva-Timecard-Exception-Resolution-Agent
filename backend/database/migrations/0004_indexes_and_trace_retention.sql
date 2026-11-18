-- Indexes for the manager's exception list, and a retention boundary for model text.
-- Track A, 2026-11-18.

-- The list filters by the employees assigned to a manager and by work date, and orders
-- problems first. The status subqueries are already served: decisions by its partial unique
-- index on (exception_id) WHERE decision = 'approve', escalations by its primary key.
CREATE INDEX exceptions_employee_work_date ON exceptions (employee_id, work_date);
CREATE INDEX exceptions_list_order ON exceptions ((severity <> 'problem'), work_date, exception_id);

-- The assignment check looks an employee up for one manager; the primary key starts with
-- manager_id, so it cannot serve that direction.
CREATE INDEX manager_assignments_employee ON manager_assignments (employee_id, manager_id);

-- Detection reads every approved correction for an employee to build the effective timecard.
CREATE INDEX corrections_employee ON corrections (employee_id);

-- ------------------------------------------------------------------ model text retention
--
-- llm_traces is append-only because it is audit evidence: which model, which prompt, how long.
-- The model's raw text is different. It can contain whatever the employee wrote in a note, it is
-- the largest column by far, and it is the part a retention policy will want to remove. Keeping it
-- in an append-only table meant it could never be deleted at all.
--
-- It moves to its own table, which has no append-only trigger, so a retention job can purge it
-- while the trace itself stays immutable. A purged trace is still provable: provider, model,
-- prompt hash, attempts, latency and any error remain.

CREATE TABLE llm_raw_outputs (
    trace_id     text PRIMARY KEY REFERENCES llm_traces ON DELETE RESTRICT,
    raw_outputs  text NOT NULL,                -- JSON array of the model's replies
    parse_errors text NOT NULL,                -- JSON array of schema failures
    created_at   timestamptz NOT NULL
);

INSERT INTO llm_raw_outputs (trace_id, raw_outputs, parse_errors, created_at)
SELECT trace_id, raw_outputs, parse_errors, created_at FROM llm_traces;

ALTER TABLE llm_traces DROP COLUMN raw_outputs, DROP COLUMN parse_errors;
