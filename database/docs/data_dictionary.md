# Resolva Database Data Dictionary

Comprehensive schema catalog detailing all 11 tables, column definitions, constraints, relationships, and enumerations in the `shiftsense.db` SQLite database.

---

## 1. Enumerations Catalog

### `PayType`
Represents the compensation basis of an employee.
- `hourly`: Non-exempt worker eligible for overtime and statutory meal-break premiums.
- `salary`: Exempt salaried employee subject to minimum shift attendance requirements.

### `PunchType`
Represents the direction and nature of a clock punch event.
- `in`: Shift start clock-in.
- `out`: Shift end clock-out.
- `break_start`: Clock-out for a meal or rest period.
- `break_end`: Clock-in returning from a meal or rest period.

### `PunchSource`
Represents the originating hardware or software channel of the punch telemetry.
- `badge`: Physical RFID/NFC wall-mounted time clock tap.
- `mobile`: Employee self-service mobile app punch (geofenced).
- `web`: Web portal self-service clock punch.
- `biometric`: Fingerprint/facial recognition hardware terminal.

### `ExceptionSeverity`
Operational priority level for manager triage.
- `low`: Informational variance (e.g., minor tardiness under grace threshold).
- `medium`: Standard anomaly requiring supervisor acknowledgment (e.g., late arrival > 15 min).
- `high`: Missing punch or potential meal break compliance violation.
- `critical`: Unauthorized overtime or statutory labor law breach.

### `ExceptionStatus`
Lifecycle state of an anomaly.
- `open`: Newly detected exception awaiting review or proposal generation.
- `resolved`: Exception successfully resolved by an approved manager correction.
- `dismissed`: Exception deemed benign and dismissed by a supervisor.

### `AuditActor`
The entity responsible for initiating a state transition.
- `SYSTEM`: Automated batch detection engine or scheduled cron job.
- `RESOLVA_AI`: AI proposal generation service (Gemini or deterministic rule engine).
- `MANAGER`: Human supervisor acting in the review portal (e.g., `MGR-1049`).

---

## 2. Relational Tables

### 2.1 Table: `organization`
Top-level corporate tenant.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique identifier. |
| `name` | `VARCHAR(255)` | No | — | Legal business entity name (e.g., "ShiftSense Global Inc."). |
| `code` | `VARCHAR(50)` | No | `UNIQUE` | Unique business code (e.g., "SHIFTSENSE-CORP"). |
| `created_at` | `DATETIME` | No | `DEFAULT CURRENT_TIMESTAMP` | Organization registration timestamp. |

---

### 2.2 Table: `location`
Physical operating facility or store branch.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique identifier. |
| `organization_id` | `INTEGER` | No | `FOREIGN KEY -> organization(id)` | Parent organization reference. |
| `name` | `VARCHAR(255)` | No | — | Facility display name (e.g., "Bengaluru Tech Center"). |
| `city` | `VARCHAR(255)` | No | — | Municipality/City name. |
| `country` | `VARCHAR(255)` | No | — | Sovereign nation code or name (e.g., "India", "USA"). |
| `timezone` | `VARCHAR(100)` | No | — | IANA timezone string (e.g., "Asia/Kolkata", "America/Chicago"). |

---

### 2.3 Table: `policy_packs`
Statutory compliance ruleset governing an employee cohort.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique identifier. |
| `code` | `VARCHAR(50)` | No | `UNIQUE(code, version)` | Policy identifier (e.g., "IN-KA", "US-FED"). |
| `name` | `VARCHAR(255)` | No | — | Human-readable ruleset title. |
| `version` | `VARCHAR(50)` | No | `UNIQUE(code, version)` | Semantic version string (e.g., "2026.1"). |
| `jurisdiction` | `VARCHAR(100)` | No | — | Governing jurisdiction (e.g., "Karnataka, India", "Federal USA"). |
| `is_active` | `BOOLEAN` | No | `DEFAULT 1` | Active availability flag. |

---

### 2.4 Table: `policy_clause`
Granular statutory articles and CBA clauses referenced in AI rationales.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique identifier. |
| `policy_pack_id` | `INTEGER` | No | `FOREIGN KEY -> policy_packs(id)` | Parent policy pack reference. |
| `clause_id` | `VARCHAR(100)` | No | `UNIQUE(policy_pack_id, clause_id)` | Unique clause slug (e.g., "US-FED-MEAL-BREAK-01"). |
| `section` | `VARCHAR(100)` | Yes | — | Statutory section number (e.g., "Section 12(1)"). |
| `content` | `TEXT` | No | — | Authoritative statutory or policy text. |
| `source_doc` | `VARCHAR(255)` | Yes | — | Official source legislation or handbook citation. |

---

### 2.5 Table: `employee`
Workforce members subject to timecard tracking.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique employee badge/ID. |
| `name` | `VARCHAR(255)` | No | — | Full legal employee name. |
| `location_id` | `INTEGER` | No | `FOREIGN KEY -> location(id)` | Assigned home workplace location. |
| `job` | `VARCHAR(255)` | No | — | Job title (e.g., "Registered Nurse", "Warehouse Associate"). |
| `pay_type` | `VARCHAR(8)` | No | Enum: `hourly`, `salary` | Compensation classification. |
| `policy_pack_id` | `INTEGER` | No | `FOREIGN KEY -> policy_packs(id)` | Governing jurisdictional policy pack. |
| `manager_id` | `INTEGER` | Yes | `FOREIGN KEY -> employee(id)` | Reporting supervisor (self-referencing). |

---

### 2.6 Table: `shift`
Scheduled working time windows.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique shift schedule identifier. |
| `employee_id` | `INTEGER` | No | `FOREIGN KEY -> employee(id)` | Scheduled employee reference. |
| `start` | `DATETIME` | No | — | Shift start timestamp. |
| `end` | `DATETIME` | No | `CHECK(end > start)` | Shift end timestamp (must follow start). |
| `planned_break_min`| `INTEGER` | No | `CHECK(planned_break_min >= 0)` | Planned non-paid meal break minutes (default: 30). |

---

### 2.7 Table: `punch`
Hardware clock events. **Strictly Immutable: Read-Only.**

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique hardware punch record identifier. |
| `employee_id` | `INTEGER` | No | `FOREIGN KEY -> employee(id)` | Clocking employee reference. |
| `ts` | `DATETIME` | No | — | Exact hardware timestamp of the badge tap. |
| `type` | `VARCHAR(11)` | No | Enum: `in`, `out`, `break_start`, `break_end` | Punch direction/type. |
| `source` | `VARCHAR(6)` | No | Enum: `badge`, `mobile`, `web`, `biometric` | Capture medium. |
| `device_id` | `VARCHAR(255)` | Yes | — | Physical terminal serial number or client IP. |

---

### 2.8 Table: `exception_record`
Detected timecard anomalies identified by the deterministic detection engine.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique exception identifier. |
| `code` | `VARCHAR(100)` | No | — | Anomaly code (e.g., `MISSED_IN_PUNCH`, `MEAL_BREAK_VIOLATION`). |
| `severity` | `VARCHAR(8)` | No | Enum: `low`, `medium`, `high`, `critical` | Triage severity level. |
| `employee_id` | `INTEGER` | No | `FOREIGN KEY -> employee(id)` | Affected employee reference. |
| `work_date` | `DATE` | No | — | Work date of the shift containing the variance. |
| `rule_version` | `VARCHAR(50)` | No | — | Semantic version of the detection rule executed. |
| `evidence` | `JSON` | No | — | JSON payload with anomaly metrics, timestamps, and delta hours. |
| `status` | `VARCHAR(9)` | No | Enum: `open`, `resolved`, `dismissed` | Current lifecycle status. |

---

### 2.9 Table: `proposal`
AI/engine-generated resolution proposals with guardrail verification results.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique proposal identifier. |
| `exception_id` | `INTEGER` | No | `FOREIGN KEY -> exception_record(id)` | Target exception reference. |
| `actions` | `JSON` | No | — | Array of proposed resolution actions (e.g., `INSERT_PUNCH`, `FLAG_MEAL_PREMIUM`). |
| `rationale` | `VARCHAR` | No | — | Human-readable explanation and legal context. |
| `citations` | `JSON` | No | — | Array of referenced `policy_clause.clause_id` values. |
| `confidence` | `FLOAT` | No | `CHECK(confidence >= 0.0 AND confidence <= 1.0)` | Statistical confidence score. |
| `model_id` | `VARCHAR(100)`| Yes | — | Engine identifier (e.g., `demo-rule-engine-v1`, `gemini-1.5-pro`). |
| `prompt_hash` | `VARCHAR(128)`| Yes | — | SHA-256 hash of context payload for reproducibility. |
| `validator_result` | `JSON` | Yes | — | Structured output from deterministic guardrails. |
| `gate_decision`| `VARCHAR(50)` | Yes | — | Automated gate outcome: `manual_review` or `auto_apply`. |

---

### 2.10 Table: `correction`
Manager-approved timecard adjustments. Represents the audit-compliant delta state.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique correction adjustment identifier. |
| `proposal_id` | `INTEGER` | Yes | `FOREIGN KEY -> proposal(id)` | Originating proposal (null if manual). |
| `actions` | `JSON` | No | — | Final applied action payload. |
| `applied_by` | `VARCHAR(100)`| No | — | Manager identifier (e.g., `MGR-1049`). |
| `reason_code` | `VARCHAR(50)` | No | — | Reason code (e.g., `MANAGER_APPROVED_AI_PROPOSAL`). |
| `comment` | `VARCHAR` | Yes | — | Optional manager justification or notes. |
| `ts` | `DATETIME` | No | `DEFAULT CURRENT_TIMESTAMP` | Timestamp of manager approval. |

---

### 2.11 Table: `audit_event`
Append-only cryptographic ledger of system and supervisor events.

| Column | Type | Nullable | Constraints | Description |
|---|---|---|---|---|
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Sequential event identifier. |
| `actor` | `VARCHAR` | No | — | Originating actor: `SYSTEM`, `RESOLVA_AI`, or manager ID. |
| `action` | `VARCHAR(100)`| No | — | Action verb (e.g., `PROPOSAL_APPROVED`, `EXCEPTION_DISMISSED`). |
| `entity_ref` | `VARCHAR(255)`| No | — | Entity URI (e.g., `proposal:7`, `exception:2`). |
| `before` | `JSON` | Yes | — | JSON snapshot of entity state prior to mutation. |
| `after` | `JSON` | Yes | — | JSON snapshot of entity state after mutation. |
| `trace_id` | `VARCHAR(128)`| No | — | Distributed trace correlation identifier. |
| `ts` | `DATETIME` | No | `DEFAULT CURRENT_TIMESTAMP` | Immutable event timestamp. |
