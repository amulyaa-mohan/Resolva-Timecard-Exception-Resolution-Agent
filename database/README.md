# Resolva Database Implementation

This directory represents the independent database contribution for **Resolva — Timecard Exception Resolution Agent**, developed for the Dayforce AI Innovation Challenge.

It provides a comprehensive, deterministic, and compliance-ready persistence layer supporting automated timecard anomaly detection, statutory labor law retrieval, AI resolution proposal generation, deterministic guardrails, supervisor approval workflows, and an immutable audit trail.

---

## 1. Directory Structure

```
database/
├── README.md                     # Main database module documentation and quickstart guide
├── AGENTS.md                     # Operational constraints and guidelines for AI agents
├── docs/                         # Detailed architecture, ERD, and data dictionary
│   ├── architecture.md           # Concurrency, SQLite tuning, and SQLModel design
│   ├── data_dictionary.md        # Comprehensive catalog of all 11 tables and enums
│   ├── erd.md                    # Visual Entity-Relationship Diagram (Mermaid)
│   ├── immutability_and_audit.md # Punch immutability and append-only ledger specs
│   └── seed_data_guide.md        # Breakdown of seeded organizational hierarchy & punches
├── migrations/                   # Database DDL migrations and schema scripts
│   ├── 001_initial_schema.sql    # Pure SQLite DDL for all 11 tables and 53 indexes
│   ├── apply_migrations.py       # Python migration runner with foreign key enforcement
│   └── README.md                 # Migration guide and versioning guidelines
├── schema/                       # SQLModel table models and database connection
│   ├── __init__.py               # Re-exports all 11 entities and domain enums
│   ├── database.py               # SQLModel engine, session generator, and table setup
│   ├── organization.py           # Organization model
│   ├── location.py               # Operational location & timezone model
│   ├── policy_pack.py            # Jurisdictional policy pack model
│   ├── policy_clause.py          # Granular statutory / CBA article model
│   ├── employee.py               # Employee profile and manager hierarchy model
│   ├── shift.py                  # Scheduled work shift model
│   ├── punch.py                  # Hardware clock punch model (Strictly Immutable)
│   ├── exception.py              # Detected timecard exception record model
│   ├── proposal.py               # AI proposal & guardrail verification model
│   ├── correction.py             # Applied timecard adjustment delta model
│   └── audit_event.py            # Append-only cryptographic audit event model
└── seeds/                        # Realistic demo data and verification scripts
    ├── seed.py                   # Initial base database seeder (398 punches, 7 anomaly types)
    ├── expand_seed_data.py       # Idempotent expansion seeder for complete college-demo scale
    ├── verify_seed.py            # Automated integrity and foreign key validation script
    └── policies/                 # Jurisdictional policy YAML definitions
        ├── in-ka.yaml            # Karnataka Shops & Commercial Establishments Act
        └── us-fed.yaml           # US Federal FLSA Policy Pack
```

---

## 2. Key Database Metrics (College-Demo Scale)

- **Total Relational Tables**: 11
- **Total Performance Indexes**: 53
- **Raw Clock Punches**: 398 (Strictly Immutable Hardware Baseline)
- **Timecard Exception Types Supported**: 7 (`DUPLICATE_PUNCH`, `MISSED_IN_PUNCH`, `MISSED_OUT_PUNCH`, `MEAL_BREAK_VIOLATION`, `LATE_ARRIVAL`, `EARLY_DEPARTURE`, `UNAUTHORIZED_OVERTIME`)
- **Policy Rule Packs**: 4 (`IN-KA`, `US-FED`, `US-IL`, `US-CA`)
- **Statutory Policy Clauses**: 20 (Covering all jurisdictions & anomaly categories)
- **Active Employees**: 24 (Distributed across clinical, engineering, operations, and fulfillment)
- **Work Shifts Scheduled**: 126 (Covering morning, evening, and night rotations)
- **Detected Timecard Exceptions**: 35 (Realistic anomaly distribution across employees)
- **Resolution Proposals**: 37 (AI and rule-engine proposals with confidence scores)
- **Applied Corrections**: 14 (Manager-approved adjustments preserving raw punches)
- **Audit Trail Events**: 37 (Cryptographic ledger entries with before/after state snapshots)

---

## 3. Core Architectural Principles

### 3.1 Raw Punch Immutability
Under no circumstances does Resolva modify, overwrite, or delete rows in the `punch` table:

$$\text{Count}(\text{punch}) \equiv 398 \quad (\Delta \text{Raw Punches} = 0)$$

All supervisor-approved adjustments are recorded as discrete delta entries in the `correction` table.

### 3.2 Append-Only Audit Trail
Every state change (proposal generation, supervisor approval, rejection, or exception dismissal) produces an immutable entry in `audit_event` with:
- Attributable actor (`SYSTEM`, `RESOLVA_AI`, or manager ID like `MGR-1049`).
- Exact `before` and `after` JSON state snapshots.
- Distributed correlation `trace_id`.

### 3.3 Multi-Thread Safe SQLite Configuration
The SQLite database (`shiftsense.db`) is configured with:
- `connect_args={"check_same_thread": False}` for multi-threaded FastAPI concurrency.
- `PRAGMA foreign_keys = ON;` for strict relational integrity.
- Scoped session dependency injection (`SessionDep`) preventing connection leaks.

---

## 4. Quickstart Guide

### Step 1: Install Dependencies
Ensure Python 3.10+ is available with `sqlmodel` and `pyyaml`:
```bash
pip install sqlmodel pyyaml
```

### Step 2: Apply Migrations (Optional / Standalone)
To initialize the SQLite schema directly via raw DDL:
```bash
python database/migrations/apply_migrations.py
```

### Step 3: Populate Idempotent Seed Data
To populate the database with realistic organizations, employees, shifts, punches, and policy clauses:
```bash
python database/seeds/seed.py
```

### Step 4: Verify Database Health & Integrity
Run the automated verification suite to confirm table counts, foreign keys, and punch immutability:
```bash
python database/seeds/verify_seed.py
```

Expected output:
```
================================================================================
       RESOLVA DATABASE INTEGRITY & SEED VERIFICATION
       Target: .../backend/shiftsense.db
================================================================================

--- Integrity Verification Results ---
  • Organization Count (>= 1)                     : [PASS] (Found 2)
  • Location Count (>= 2)                         : [PASS] (Found 3)
  • Policy Pack Count (>= 2)                      : [PASS] (Found 3)
  • Policy Clause Count (>= 14)                   : [PASS] (Found 14)
  • Employee Count (>= 15)                        : [PASS] (Found 16)
  • Shift Count (>= 100)                          : [PASS] (Found 101)
  • Raw Punch Count (== 398 strictly immutable)   : [PASS] (Found 398)
  • Location -> Organization FK                   : [PASS] (0 orphaned)
  • Employee -> Location/PolicyPack FK            : [PASS] (0 orphaned)
  • Shift -> Employee FK                          : [PASS] (0 orphaned)
  • Punch -> Employee FK                          : [PASS] (0 orphaned)
  • Policy Clause -> PolicyPack FK                : [PASS] (0 orphaned)
================================================================================
      ALL DATABASE INTEGRITY CHECKS PASSED (100% HEALTHY)
================================================================================
```
