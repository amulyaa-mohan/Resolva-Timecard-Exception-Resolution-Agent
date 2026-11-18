-- Resolva initial schema (PostgreSQL 15+). Track A, DB-01/DB-02 draft for review.
-- All instants are timestamptz (stored UTC). Local dates (work_date) are in the employee's
-- timezone, recorded on the employee row. Raw punches, decisions, corrections and audit
-- events are append-only; corrections never rewrite punches.

-- ------------------------------------------------------------------ people and access

CREATE TABLE managers (
    manager_id   text PRIMARY KEY CHECK (manager_id <> ''),
    timezone     text NOT NULL DEFAULT 'UTC'
);

CREATE TABLE employees (
    employee_id     text PRIMARY KEY CHECK (employee_id <> ''),
    location_id     text NOT NULL,
    jurisdiction    text NOT NULL,             -- policy jurisdiction, e.g. 'IN-KA'
    timezone        text NOT NULL,             -- IANA name, e.g. 'Asia/Kolkata'
    worker_category text
);

CREATE TABLE manager_assignments (
    manager_id  text NOT NULL REFERENCES managers ON DELETE RESTRICT,
    employee_id text NOT NULL REFERENCES employees ON DELETE RESTRICT,
    valid_from  timestamptz NOT NULL DEFAULT now(),
    valid_to    timestamptz,
    PRIMARY KEY (manager_id, employee_id, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- ------------------------------------------------------------------ raw attendance

CREATE TABLE scheduled_shifts (
    shift_id          text PRIMARY KEY,
    employee_id       text NOT NULL REFERENCES employees ON DELETE RESTRICT,
    start_at          timestamptz NOT NULL,
    end_at            timestamptz NOT NULL,
    planned_break_min integer NOT NULL CHECK (planned_break_min >= 0),
    CHECK (end_at > start_at)
);
CREATE INDEX scheduled_shifts_employee ON scheduled_shifts (employee_id, start_at);

CREATE TABLE punches (
    punch_id        text PRIMARY KEY,
    employee_id     text NOT NULL REFERENCES employees ON DELETE RESTRICT,
    ts              timestamptz NOT NULL,
    type            text NOT NULL CHECK (type IN ('in', 'out', 'break_start', 'break_end')),
    source          text NOT NULL CHECK (source IN ('kiosk', 'mobile', 'web', 'import')),
    device_id       text,
    source_event_id text NOT NULL,             -- id in the source system; dedupes re-imports
    import_batch_id text,
    received_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, source_event_id)
);
CREATE INDEX punches_employee_ts ON punches (employee_id, ts);

CREATE TABLE employee_notes (
    note_id      text PRIMARY KEY,
    employee_id  text NOT NULL REFERENCES employees ON DELETE RESTRICT,
    text         text NOT NULL CHECK (char_length(text) <= 1000),
    submitted_at timestamptz NOT NULL
);

-- ------------------------------------------------------------------ exceptions

CREATE TABLE exceptions (
    exception_id        text PRIMARY KEY,
    employee_id         text NOT NULL REFERENCES employees ON DELETE RESTRICT,
    shift_id            text REFERENCES scheduled_shifts ON DELETE RESTRICT,
    code                text NOT NULL CHECK (code IN ('MISSING_PUNCH', 'OVERLAPPING_SHIFT',
                            'MEAL_BREAK_BREACH', 'OVERTIME_RISK', 'SPREAD_OVER_BREACH',
                            'SCHEDULE_DEVIATION')),
    severity            text NOT NULL CHECK (severity IN ('problem', 'warning')),
    work_date           date NOT NULL,         -- local shift-start date
    status              text NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'escalated', 'resolved', 'dismissed')),
    rule_version        text NOT NULL,
    detection_details   jsonb NOT NULL DEFAULT '{}'::jsonb,
    correction_revision integer NOT NULL DEFAULT 0 CHECK (correction_revision >= 0),
    detected_at         timestamptz NOT NULL DEFAULT now()
);
-- At most one live exception of a kind per employee and work date.
CREATE UNIQUE INDEX exceptions_one_live
    ON exceptions (employee_id, work_date, code) WHERE status IN ('open', 'escalated');

-- The evidence a detection used: the work-date punches and the employee's notes.
CREATE TABLE exception_punches (
    exception_id text NOT NULL REFERENCES exceptions ON DELETE RESTRICT,
    punch_id     text NOT NULL REFERENCES punches ON DELETE RESTRICT,
    PRIMARY KEY (exception_id, punch_id)
);
CREATE TABLE exception_notes (
    exception_id text NOT NULL REFERENCES exceptions ON DELETE RESTRICT,
    note_id      text NOT NULL REFERENCES employee_notes ON DELETE RESTRICT,
    PRIMARY KEY (exception_id, note_id)
);

-- ------------------------------------------------------------------ decisions and audit

CREATE TABLE decisions (
    decision_id      text PRIMARY KEY,
    exception_id     text NOT NULL REFERENCES exceptions ON DELETE RESTRICT,
    manager_id       text NOT NULL REFERENCES managers ON DELETE RESTRICT,
    decision         text NOT NULL CHECK (decision IN ('approve', 'reject')),
    source           text NOT NULL CHECK (source IN ('ai_proposal', 'manager_edit', 'none')),
    evidence_version text NOT NULL,
    idempotency_key  text NOT NULL UNIQUE,
    request_hash     text NOT NULL,
    response_json    jsonb NOT NULL,
    decided_at       timestamptz NOT NULL
);
CREATE UNIQUE INDEX decisions_one_approval ON decisions (exception_id) WHERE decision = 'approve';

CREATE TABLE corrections (
    correction_id text PRIMARY KEY,
    decision_id   text NOT NULL UNIQUE REFERENCES decisions ON DELETE RESTRICT,
    exception_id  text NOT NULL REFERENCES exceptions ON DELETE RESTRICT,
    employee_id   text NOT NULL REFERENCES employees ON DELETE RESTRICT,
    actions_json  jsonb NOT NULL,
    created_at    timestamptz NOT NULL
);

CREATE TABLE audit_events (
    seq          bigserial PRIMARY KEY,
    event_id     text NOT NULL UNIQUE,
    occurred_at  text NOT NULL,                -- ISO-8601 UTC string, hashed as written
    actor_type   text NOT NULL CHECK (actor_type IN ('manager', 'system', 'ai')),
    actor_id     text NOT NULL,
    event_type   text NOT NULL,
    exception_id text NOT NULL REFERENCES exceptions ON DELETE RESTRICT,
    -- Deferred: the event and its decision are written in the same transaction, event first.
    decision_id  text REFERENCES decisions ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    payload_json text NOT NULL,                -- canonical JSON, hashed as written
    prev_hash    text NOT NULL,
    hash         text NOT NULL UNIQUE
);
CREATE INDEX audit_events_exception ON audit_events (exception_id, seq);

-- Trusted per-day totals for weekly/quarterly limits (provisioning, imports, corrections).
CREATE TABLE day_totals (
    employee_id     text NOT NULL REFERENCES employees ON DELETE RESTRICT,
    work_date       date NOT NULL,
    worked_hours    double precision NOT NULL CHECK (worked_hours >= 0),
    scheduled_hours double precision NOT NULL CHECK (scheduled_hours >= 0),
    evidence_final  boolean NOT NULL,          -- the day is over and its punches are all in
    complete        boolean NOT NULL,          -- final AND worked_hours is known (pairs closed)
    source          text NOT NULL,
    updated_at      timestamptz NOT NULL,
    PRIMARY KEY (employee_id, work_date),
    CHECK (evidence_final OR NOT complete)
);

-- ------------------------------------------------------------------ append-only enforcement

CREATE FUNCTION resolva_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE TRIGGER punches_append_only BEFORE UPDATE OR DELETE ON punches
    FOR EACH ROW EXECUTE FUNCTION resolva_append_only();
CREATE TRIGGER decisions_append_only BEFORE UPDATE OR DELETE ON decisions
    FOR EACH ROW EXECUTE FUNCTION resolva_append_only();
CREATE TRIGGER corrections_append_only BEFORE UPDATE OR DELETE ON corrections
    FOR EACH ROW EXECUTE FUNCTION resolva_append_only();
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION resolva_append_only();
CREATE TRIGGER punches_no_truncate BEFORE TRUNCATE ON punches
    FOR EACH STATEMENT EXECUTE FUNCTION resolva_append_only();
CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION resolva_append_only();
