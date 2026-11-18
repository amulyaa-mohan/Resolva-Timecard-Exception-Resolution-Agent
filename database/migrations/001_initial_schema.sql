-- ==============================================================================
-- Resolva Timecard Exception Resolution Agent
-- Migration 001: Initial Database Schema DDL
-- Database Dialect: SQLite 3 / SQLModel / SQLAlchemy
-- Tables: 11 | Indexes: 53 | Constraints: Foreign Keys, Unique & Checks
-- ==============================================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------------------
-- 1. Organization & Core Workplace Hierarchy
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS organization (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_organization_code ON organization (code);
CREATE INDEX IF NOT EXISTS ix_organization_id ON organization (id);
CREATE INDEX IF NOT EXISTS ix_organization_name ON organization (name);

-- ------------------------------------------------------------------------------
-- 2. Physical & Operational Locations
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS location (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(255) NOT NULL,
    country VARCHAR(255) NOT NULL,
    timezone VARCHAR(100) NOT NULL,
    FOREIGN KEY (organization_id) REFERENCES organization (id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_location_id ON location (id);
CREATE INDEX IF NOT EXISTS ix_location_organization_id ON location (organization_id);
CREATE INDEX IF NOT EXISTS ix_location_name ON location (name);
CREATE INDEX IF NOT EXISTS ix_location_city ON location (city);
CREATE INDEX IF NOT EXISTS ix_location_country ON location (country);

-- ------------------------------------------------------------------------------
-- 3. Policy Packs (Jurisdictional Compliance Rules)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS policy_packs (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    jurisdiction VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    CONSTRAINT uq_policy_packs_code_version UNIQUE (code, version)
);

CREATE INDEX IF NOT EXISTS ix_policy_packs_id ON policy_packs (id);
CREATE INDEX IF NOT EXISTS ix_policy_packs_code ON policy_packs (code);
CREATE INDEX IF NOT EXISTS ix_policy_packs_name ON policy_packs (name);
CREATE INDEX IF NOT EXISTS ix_policy_packs_version ON policy_packs (version);
CREATE INDEX IF NOT EXISTS ix_policy_packs_jurisdiction ON policy_packs (jurisdiction);

-- ------------------------------------------------------------------------------
-- 4. Policy Clauses (Granular Statutory / CBA Articles)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS policy_clause (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    policy_pack_id INTEGER NOT NULL,
    clause_id VARCHAR(100) NOT NULL,
    section VARCHAR(100),
    content TEXT NOT NULL,
    source_doc VARCHAR(255),
    CONSTRAINT uq_policy_clause_pack_clause UNIQUE (policy_pack_id, clause_id),
    FOREIGN KEY (policy_pack_id) REFERENCES policy_packs (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_policy_clause_id ON policy_clause (id);
CREATE INDEX IF NOT EXISTS ix_policy_clause_policy_pack_id ON policy_clause (policy_pack_id);
CREATE INDEX IF NOT EXISTS ix_policy_clause_clause_id ON policy_clause (clause_id);

-- ------------------------------------------------------------------------------
-- 5. Employees & Reporting Structure
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    location_id INTEGER NOT NULL,
    job VARCHAR(255) NOT NULL,
    pay_type VARCHAR(8) NOT NULL, -- 'hourly', 'salary'
    policy_pack_id INTEGER NOT NULL,
    manager_id INTEGER,
    FOREIGN KEY (location_id) REFERENCES location (id) ON DELETE RESTRICT,
    FOREIGN KEY (policy_pack_id) REFERENCES policy_packs (id) ON DELETE RESTRICT,
    FOREIGN KEY (manager_id) REFERENCES employee (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_employee_id ON employee (id);
CREATE INDEX IF NOT EXISTS ix_employee_name ON employee (name);
CREATE INDEX IF NOT EXISTS ix_employee_location_id ON employee (location_id);
CREATE INDEX IF NOT EXISTS ix_employee_job ON employee (job);
CREATE INDEX IF NOT EXISTS ix_employee_pay_type ON employee (pay_type);
CREATE INDEX IF NOT EXISTS ix_employee_policy_pack_id ON employee (policy_pack_id);
CREATE INDEX IF NOT EXISTS ix_employee_manager_id ON employee (manager_id);

-- ------------------------------------------------------------------------------
-- 6. Scheduled Work Shifts
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shift (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    start DATETIME NOT NULL,
    "end" DATETIME NOT NULL,
    planned_break_min INTEGER NOT NULL DEFAULT 30,
    CONSTRAINT check_shift_end_after_start CHECK ("end" > start),
    CONSTRAINT check_planned_break_min_non_negative CHECK (planned_break_min >= 0),
    FOREIGN KEY (employee_id) REFERENCES employee (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_shift_id ON shift (id);
CREATE INDEX IF NOT EXISTS ix_shift_employee_id ON shift (employee_id);
CREATE INDEX IF NOT EXISTS ix_shift_start ON shift (start);
CREATE INDEX IF NOT EXISTS ix_shift_end ON shift ("end");

-- ------------------------------------------------------------------------------
-- 7. Raw Clock Punches (Strictly Immutable Hardware/App Telemetry)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS punch (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    ts DATETIME NOT NULL,
    type VARCHAR(11) NOT NULL, -- 'in', 'out', 'break_start', 'break_end'
    source VARCHAR(6) NOT NULL, -- 'badge', 'mobile', 'web', 'biometric'
    device_id VARCHAR(255),
    FOREIGN KEY (employee_id) REFERENCES employee (id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_punch_id ON punch (id);
CREATE INDEX IF NOT EXISTS ix_punch_employee_id ON punch (employee_id);
CREATE INDEX IF NOT EXISTS ix_punch_ts ON punch (ts);
CREATE INDEX IF NOT EXISTS ix_punch_type ON punch (type);
CREATE INDEX IF NOT EXISTS ix_punch_source ON punch (source);

-- ------------------------------------------------------------------------------
-- 8. Detected Timecard Exceptions
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exception_record (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(100) NOT NULL,
    severity VARCHAR(8) NOT NULL, -- 'low', 'medium', 'high', 'critical'
    employee_id INTEGER NOT NULL,
    work_date DATE NOT NULL,
    rule_version VARCHAR(50) NOT NULL,
    evidence JSON NOT NULL,
    status VARCHAR(9) NOT NULL DEFAULT 'open', -- 'open', 'resolved', 'dismissed'
    FOREIGN KEY (employee_id) REFERENCES employee (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_exception_record_id ON exception_record (id);
CREATE INDEX IF NOT EXISTS ix_exception_record_code ON exception_record (code);
CREATE INDEX IF NOT EXISTS ix_exception_record_severity ON exception_record (severity);
CREATE INDEX IF NOT EXISTS ix_exception_record_employee_id ON exception_record (employee_id);
CREATE INDEX IF NOT EXISTS ix_exception_record_work_date ON exception_record (work_date);
CREATE INDEX IF NOT EXISTS ix_exception_record_rule_version ON exception_record (rule_version);
CREATE INDEX IF NOT EXISTS ix_exception_record_status ON exception_record (status);

-- ------------------------------------------------------------------------------
-- 9. AI Resolution Proposals
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proposal (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    exception_id INTEGER NOT NULL,
    actions JSON NOT NULL,
    rationale VARCHAR NOT NULL,
    citations JSON NOT NULL,
    confidence FLOAT NOT NULL,
    model_id VARCHAR(100),
    prompt_hash VARCHAR(128),
    validator_result JSON,
    gate_decision VARCHAR(50),
    CONSTRAINT check_proposal_confidence_range CHECK (confidence >= 0.0 AND confidence <= 1.0),
    FOREIGN KEY (exception_id) REFERENCES exception_record (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_proposal_id ON proposal (id);
CREATE INDEX IF NOT EXISTS ix_proposal_exception_id ON proposal (exception_id);
CREATE INDEX IF NOT EXISTS ix_proposal_confidence ON proposal (confidence);

-- ------------------------------------------------------------------------------
-- 10. Applied Timecard Corrections (Non-destructive delta tracking)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS correction (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER,
    actions JSON NOT NULL,
    applied_by VARCHAR(100) NOT NULL,
    reason_code VARCHAR(50) NOT NULL,
    comment VARCHAR,
    ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proposal_id) REFERENCES proposal (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_correction_id ON correction (id);
CREATE INDEX IF NOT EXISTS ix_correction_proposal_id ON correction (proposal_id);
CREATE INDEX IF NOT EXISTS ix_correction_applied_by ON correction (applied_by);
CREATE INDEX IF NOT EXISTS ix_correction_reason_code ON correction (reason_code);
CREATE INDEX IF NOT EXISTS ix_correction_ts ON correction (ts);

-- ------------------------------------------------------------------------------
-- 11. Immutable Audit Ledger
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_event (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    actor VARCHAR NOT NULL,
    action VARCHAR(100) NOT NULL,
    entity_ref VARCHAR(255) NOT NULL,
    "before" JSON,
    "after" JSON,
    trace_id VARCHAR(128) NOT NULL,
    ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_event_id ON audit_event (id);
CREATE INDEX IF NOT EXISTS ix_audit_event_actor ON audit_event (actor);
CREATE INDEX IF NOT EXISTS ix_audit_event_action ON audit_event (action);
CREATE INDEX IF NOT EXISTS ix_audit_event_entity_ref ON audit_event (entity_ref);
CREATE INDEX IF NOT EXISTS ix_audit_event_trace_id ON audit_event (trace_id);
CREATE INDEX IF NOT EXISTS ix_audit_event_ts ON audit_event (ts);
