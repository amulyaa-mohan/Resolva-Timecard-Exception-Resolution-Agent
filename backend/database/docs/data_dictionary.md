# Resolva Database Data Dictionary

Source of truth: `backend/database/migrations/*.sql`. Enumerated values repeat
`backend/app/core/contracts.py` so the database rejects an unexpected value on its own.
All instants are `timestamptz` stored in UTC. All `*_id` columns are business identifiers (text).

## 1. Enumerations

| Enumeration | Values | Used by |
| --- | --- | --- |
| `PunchType` | `in`, `out`, `break_start`, `break_end` | `punches.type` |
| `PunchSource` | `kiosk`, `mobile`, `web`, `import` | `punches.source` |
| `ExceptionCode` | `MISSING_PUNCH`, `OVERLAPPING_SHIFT`, `MEAL_BREAK_BREACH`, `OVERTIME_RISK`, `SPREAD_OVER_BREACH`, `SCHEDULE_DEVIATION` | `exceptions.code` |
| `Severity` | `problem`, `warning` | `exceptions.severity` |
| `ExceptionStatus` | `open`, `escalated`, `resolved`, `dismissed` (detection found the problem gone; it reopens if the problem returns) | `exceptions.status` |
| `DecisionType` | `approve`, `reject`, `escalate` | `decisions.decision` |
| `DecisionSource` | `ai_proposal`, `manager_edit`, `none` | `decisions.source` |
| `GateStatus` | `eligible`, `blocked`, `escalated` | `proposals.status` |
| `ActorType` | `manager`, `system`, `ai` | `audit_events.actor_type` |
| `EscalationSource` | `pipeline`, `manager` | `escalations.source` |
| `PayType` | `hourly`, `salary` | `employees.pay_type` |

## 2. Tables

### 2.1 `organizations`
| Column | Type | Notes |
| --- | --- | --- |
| `org_id` | text PK | non-empty |
| `name` | text | |
| `created_at` | timestamptz | defaults to `now()` |

### 2.2 `locations`
| Column | Type | Notes |
| --- | --- | --- |
| `location_id` | text PK | matches `employees.location_id` |
| `org_id` | text FK -> organizations | RESTRICT |
| `name`, `city`, `country` | text | display |
| `timezone` | text | for seeding new employees; the employee's own timezone stays authoritative |

### 2.3 `managers`
| Column | Type | Notes |
| --- | --- | --- |
| `manager_id` | text PK | from the authenticated credential, never from a request body |
| `timezone` | text | used for date presets such as THIS_WEEK |

### 2.4 `employees`
| Column | Type | Notes |
| --- | --- | --- |
| `employee_id` | text PK | |
| `location_id` | text | site id |
| `jurisdiction` | text | selects the policy pack, e.g. `IN-KA` |
| `timezone` | text | IANA name; defines local work dates |
| `worker_category` | text | optional |
| `full_name`, `job_title` | text | display only (migration 0003) |
| `pay_type` | text | `hourly` or `salary`; display only |

### 2.5 `manager_assignments`
| Column | Type | Notes |
| --- | --- | --- |
| `manager_id`, `employee_id` | text FK | RESTRICT |
| `valid_from`, `valid_to` | timestamptz | `valid_to` null means current; CHECK `valid_to > valid_from` |

PK `(manager_id, employee_id, valid_from)`. Every read and write checks the window, so ending an
assignment removes access without deleting history.

### 2.6 `scheduled_shifts`
| Column | Type | Notes |
| --- | --- | --- |
| `shift_id` | text PK | |
| `employee_id` | text FK | RESTRICT |
| `start_at`, `end_at` | timestamptz | CHECK `end_at > start_at` |
| `planned_break_min` | integer | >= 0; a plan, never evidence that a break happened |

### 2.7 `punches` (append-only)
| Column | Type | Notes |
| --- | --- | --- |
| `punch_id` | text PK | |
| `employee_id` | text FK | RESTRICT |
| `ts` | timestamptz | the instant it happened |
| `type` | text | `PunchType` |
| `source` | text | `PunchSource` |
| `device_id` | text | optional |
| `source_event_id` | text | id in the source system |
| `import_batch_id` | text | which import wrote it |
| `received_at` | timestamptz | defaults to `now()` |

`UNIQUE (source, source_event_id)` makes a re-import a no-op. Triggers reject UPDATE, DELETE and
TRUNCATE.

### 2.8 `employee_notes`
| Column | Type | Notes |
| --- | --- | --- |
| `note_id` | text PK | |
| `employee_id` | text FK | RESTRICT |
| `text` | text | CHECK length <= 1000; untrusted input, never an instruction |
| `submitted_at` | timestamptz | |

### 2.9 `exceptions`
| Column | Type | Notes |
| --- | --- | --- |
| `exception_id` | text PK | deterministic: `EX-<employee>-<date>-<code>` |
| `employee_id` | text FK | RESTRICT |
| `shift_id` | text FK | nullable |
| `code`, `severity`, `status` | text | enumerations above |
| `work_date` | date | the local date the session started |
| `rule_version` | text | which rule build detected it |
| `detection_details` | jsonb | why it fired |
| `correction_revision` | integer | >= 0; every approval bumps it, which makes older proposals stale |
| `detected_at` | timestamptz | |

Partial unique index `exceptions_one_live (employee_id, work_date, code) WHERE status IN ('open','escalated')`.

### 2.10 `exception_punches` / `exception_notes`
Join tables holding the evidence a detection used. PK on both columns, both FKs RESTRICT.

### 2.11 `proposals` (append-only)
| Column | Type | Notes |
| --- | --- | --- |
| `proposal_id` | text PK | |
| `exception_id` | text FK | RESTRICT |
| `requested_by` | text FK -> managers | who asked for the draft |
| `status` | text | `GateStatus` |
| `evidence_version` | text | the evidence hash it was drafted against |
| `policy_pack_id`, `policy_version`, `rule_version` | text | reconstructability |
| `proposal_json`, `validation_json`, `gate_checks_json`, `reasons_json` | text | canonical JSON |

JSON is stored as text, not jsonb, so one code path serves both this store and the demo SQLite
store; query it in the application.

### 2.12 `llm_traces` (append-only)
| Column | Type | Notes |
| --- | --- | --- |
| `trace_id` | text PK | |
| `proposal_id` | text FK | RESTRICT |
| `provider`, `model_id`, `prompt_version`, `prompt_hash` | text | which model and prompt ran |
| `retrieved_chunk_ids` | text | JSON array of clause ids |
| `attempts`, `latency_ms` | integer | |
| `error` | text | null on success |

### 2.12a `llm_raw_outputs`
| Column | Type | Notes |
| --- | --- | --- |
| `trace_id` | text PK FK -> llm_traces | RESTRICT |
| `raw_outputs`, `parse_errors` | text | JSON arrays |
| `created_at` | timestamptz | drives retention |

The one table that is **not** append-only, on purpose: model text may quote whatever an employee
wrote in a note, so retention has to be able to remove it. The trace stays, so a purged decision is
still provable. Purge with `backend/scripts/db_maintenance.py purge-traces`.

### 2.13 `decisions` (append-only)
| Column | Type | Notes |
| --- | --- | --- |
| `decision_id` | text PK | |
| `exception_id` | text FK | RESTRICT |
| `manager_id` | text FK | from the credential |
| `decision`, `source` | text | enumerations above |
| `evidence_version` | text | what the manager actually reviewed |
| `idempotency_key` | text UNIQUE | a retry replays the stored result |
| `request_hash` | text | the same key with a different body is rejected |
| `response_json` | jsonb | the stored result |
| `decided_at` | timestamptz | |

Partial unique index `decisions_one_approval (exception_id) WHERE decision = 'approve'`.

### 2.14 `corrections` (append-only)
| Column | Type | Notes |
| --- | --- | --- |
| `correction_id` | text PK | |
| `decision_id` | text FK UNIQUE | one correction per approval |
| `exception_id`, `employee_id` | text FK | RESTRICT |
| `actions_json` | jsonb | the actions exactly as approved |
| `created_at` | timestamptz | |

### 2.15 `escalations`
| Column | Type | Notes |
| --- | --- | --- |
| `exception_id` | text PK FK | first escalation wins |
| `reason` | text | |
| `source` | text | `pipeline` or `manager` |
| `escalated_at` | timestamptz | |

Status is derived, not stored twice: resolved (an approval exists) > escalated > open.

### 2.16 `audit_events` (append-only, hash-chained)
| Column | Type | Notes |
| --- | --- | --- |
| `seq` | bigserial PK | ordering |
| `event_id` | text UNIQUE | |
| `occurred_at` | text | ISO-8601 UTC, hashed exactly as written |
| `actor_type`, `actor_id` | text | `manager`, `system` or `ai` |
| `event_type` | text | `EXCEPTION_DETECTED`, `PROPOSAL_GENERATED`, `APPROVAL_BLOCKED`, `DECISION_APPROVED`, `DECISION_REJECTED`, `DECISION_ESCALATED` |
| `exception_id` | text FK | RESTRICT |
| `decision_id` | text FK | nullable, DEFERRABLE: the event is written before the decision row |
| `payload_json` | text | canonical JSON, hashed as written |
| `prev_hash`, `hash` | text | SHA-256 chain; `hash` is unique |

### 2.17 `day_totals`
| Column | Type | Notes |
| --- | --- | --- |
| `employee_id`, `work_date` | PK | one row per local work date |
| `worked_hours`, `scheduled_hours` | double precision | >= 0 |
| `evidence_final` | boolean | the day is over and its punches are all in |
| `complete` | boolean | also pairable, so the hours are known; CHECK `evidence_final OR NOT complete` |
| `source` | text | which process wrote it |
| `updated_at` | timestamptz | |

Written only by trusted server code. Missing or incomplete days make weekly and quarterly limits
undecidable, which is reported as insufficient evidence rather than assumed to be zero.

### 2.18 `schema_migrations`
`version` PK, `checksum`, `applied_at`. Created by the runner. An applied migration that was edited
afterwards is refused.
