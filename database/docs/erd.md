# Resolva Database Entity-Relationship Diagram (ERD)

The following Mermaid diagram visualizes the complete entity relationships, cardinalities, foreign key connections, and primary keys across the 11 tables in the Resolva database.

```mermaid
erDiagram
    ORGANIZATION ||--o{ LOCATION : "operates"
    LOCATION ||--o{ EMPLOYEE : "employs"
    POLICY_PACKS ||--o{ POLICY_CLAUSE : "contains"
    POLICY_PACKS ||--o{ EMPLOYEE : "governs"
    EMPLOYEE ||--o{ EMPLOYEE : "manages"
    EMPLOYEE ||--o{ SHIFT : "scheduled_for"
    EMPLOYEE ||--o{ PUNCH : "records"
    EMPLOYEE ||--o{ EXCEPTION_RECORD : "incurs"
    EXCEPTION_RECORD ||--o{ PROPOSAL : "generates"
    PROPOSAL ||--o| CORRECTION : "results_in"

    ORGANIZATION {
        INTEGER id PK
        VARCHAR name
        VARCHAR code UK
        DATETIME created_at
    }

    LOCATION {
        INTEGER id PK
        INTEGER organization_id FK
        VARCHAR name
        VARCHAR city
        VARCHAR country
        VARCHAR timezone
    }

    POLICY_PACKS {
        INTEGER id PK
        VARCHAR code UK
        VARCHAR name
        VARCHAR version UK
        VARCHAR jurisdiction
        BOOLEAN is_active
    }

    POLICY_CLAUSE {
        INTEGER id PK
        INTEGER policy_pack_id FK
        VARCHAR clause_id UK
        VARCHAR section
        TEXT content
        VARCHAR source_doc
    }

    EMPLOYEE {
        INTEGER id PK
        VARCHAR name
        INTEGER location_id FK
        VARCHAR job
        VARCHAR pay_type
        INTEGER policy_pack_id FK
        INTEGER manager_id FK
    }

    SHIFT {
        INTEGER id PK
        INTEGER employee_id FK
        DATETIME start
        DATETIME end
        INTEGER planned_break_min
    }

    PUNCH {
        INTEGER id PK
        INTEGER employee_id FK
        DATETIME ts
        VARCHAR type
        VARCHAR source
        VARCHAR device_id
    }

    EXCEPTION_RECORD {
        INTEGER id PK
        VARCHAR code
        VARCHAR severity
        INTEGER employee_id FK
        DATE work_date
        VARCHAR rule_version
        JSON evidence
        VARCHAR status
    }

    PROPOSAL {
        INTEGER id PK
        INTEGER exception_id FK
        JSON actions
        VARCHAR rationale
        JSON citations
        FLOAT confidence
        VARCHAR model_id
        VARCHAR prompt_hash
        JSON validator_result
        VARCHAR gate_decision
    }

    CORRECTION {
        INTEGER id PK
        INTEGER proposal_id FK
        JSON actions
        VARCHAR applied_by
        VARCHAR reason_code
        VARCHAR comment
        DATETIME ts
    }

    AUDIT_EVENT {
        INTEGER id PK
        VARCHAR actor
        VARCHAR action
        VARCHAR entity_ref
        JSON before
        JSON after
        VARCHAR trace_id
        DATETIME ts
    }
```

---

## Cardinality Summary

| Relationship | Cardinality | Business Meaning |
|---|---|---|
| `organization -> location` | $1 : N$ | An organization operates one or more physical locations. |
| `location -> employee` | $1 : N$ | An employee is assigned to a home location with an associated timezone. |
| `policy_packs -> policy_clause` | $1 : N$ | A jurisdictional policy pack groups multiple statutory clauses. |
| `policy_packs -> employee` | $1 : N$ | Each employee is governed by a statutory compliance pack based on work location. |
| `employee -> employee` | $0..1 : N$ | Self-referencing reporting hierarchy (employees report to a manager). |
| `employee -> shift` | $1 : N$ | An employee has scheduled shifts across the payroll cycle. |
| `employee -> punch` | $1 : N$ | Physical or virtual clock taps captured for an employee. |
| `employee -> exception_record` | $1 : N$ | Timecard anomalies detected against scheduled shifts and clock punches. |
| `exception_record -> proposal` | $1 : N$ | An exception can have AI resolution proposals generated for it. |
| `proposal -> correction` | $1 : 0..1$ | An approved proposal spawns exactly one timecard correction record. |
| `audit_event` | Independent Ledger | Append-only ledger linking to any entity via `entity_ref` (e.g., `proposal:1`). |
