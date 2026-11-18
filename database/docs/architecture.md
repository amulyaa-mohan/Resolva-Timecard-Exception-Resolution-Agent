# Resolva Database Architecture

## 1. Architectural Overview

The persistence layer of **Resolva — Timecard Exception Resolution Agent** is architected to provide an enterprise-grade, deterministic, and audit-compliant relational datastore for workforce management (WFM) timecard exceptions, statutory policy compliance, AI-generated resolution proposals, and managerial review workflows.

The system utilizes **SQLModel** (which unifies **Pydantic v2** validation with **SQLAlchemy 2.0** ORM capabilities) backed by an optimized **SQLite 3** relational database engine (`shiftsense.db`).

```
+----------------------------------------------------------------------------+
|                         FastAPI Application Services                       |
|   (Detection Engine, Proposal Generator, Guardrails, Resolution Service)  |
+----------------------------------------------------------------------------+
                                     |
                         [SQLModel ORM / SessionDep]
                                     |
+------------------------------------+---------------------------------------+
|                                                                            |
|   +--------------------------------------------------------------------+   |
|   |                  1. Core Workplace Hierarchy                       |   |
|   |         Organization  <---  Location  <---  Employee               |   |
|   +--------------------------------------------------------------------+   |
|                                    |                                       |
|   +--------------------------------+-----------------------------------+   |
|   |                  2. Jurisdictional Policies                        |   |
|   |                 PolicyPack  <---  PolicyClause                     |   |
|   +--------------------------------------------------------------------+   |
|                                    |                                       |
|   +--------------------------------+-----------------------------------+   |
|   |                  3. Time & Attendance Telemetry                    |   |
|   |                 Shift  &  Punch (Strictly Immutable)               |   |
|   +--------------------------------------------------------------------+   |
|                                    |                                       |
|   +--------------------------------+-----------------------------------+   |
|   |                  4. Exception Lifecycle & AI Loop                  |   |
|   |       ExceptionRecord  <---  Proposal  <---  Correction            |   |
|   +--------------------------------------------------------------------+   |
|                                    |                                       |
|   +--------------------------------+-----------------------------------+   |
|   |                  5. Compliance & Audit Ledger                      |   |
|   |                           AuditEvent                               |   |
|   +--------------------------------------------------------------------+   |
|                                                                            |
+----------------------------------------------------------------------------+
                                     |
+----------------------------------------------------------------------------+
|                    Physical SQLite Datastore: shiftsense.db                |
|                    PRAGMA foreign_keys = ON; WAL Mode Enabled              |
+----------------------------------------------------------------------------+
```

---

## 2. Table Categorization

The 11 relational tables are partitioned into 5 functional domains:

| Domain | Tables | Responsibilities |
|---|---|---|
| **Core Workplace Hierarchy** | `organization`, `location`, `employee` | Multi-tenant organization structure, physical sites, timezones, and managerial reporting hierarchies. |
| **Jurisdictional Policies** | `policy_packs`, `policy_clause` | Statutory labor laws, collective bargaining agreements (CBAs), section references, and compliance text. |
| **Time & Attendance** | `shift`, `punch` | Scheduled working hours and raw hardware badge/mobile/web clock punch events. |
| **Exception Lifecycle** | `exception_record`, `proposal`, `correction` | Detected timecard anomalies, AI-generated resolution proposals, deterministic guardrail verdicts, and approved time adjustments. |
| **Compliance & Audit Ledger** | `audit_event` | Tamper-evident, append-only record of all system events, AI outputs, and supervisor actions with before/after state diffs. |

---

## 3. SQLite Concurrency & Connection Strategy

Because Resolva serves real-time API requests alongside background batch detection and AI generation tasks, the SQLite engine is configured for high concurrency:

1. **Multi-Thread Concurrency (`check_same_thread: False`)**:
   Standard SQLite connections are bound to the originating thread. FastAPI dispatches requests across an async threadpool. Setting `connect_args={"check_same_thread": False}` allows safe connection handoffs.
2. **Per-Request Session Scoping (`SessionDep`)**:
   The `get_session()` generator yields an active `sqlmodel.Session` wrapped in a Python context manager (`with Session(engine) as session:`). This guarantees that connections are returned cleanly to the pool and transactions are closed, eliminating connection starvation and locks.
3. **Foreign Key Enforcement (`PRAGMA foreign_keys = ON`)**:
   SQLite does not enforce foreign keys by default. All migration scripts and database initialization routines explicitly issue `PRAGMA foreign_keys = ON;` to guarantee relational integrity.
4. **Strict Immutability Architecture**:
   Raw clock punches (`punch` table) are strictly read-only after creation. Under no circumstances does the resolution pipeline `UPDATE` or `DELETE` original clock punches. All adjustments are stored in the discrete `correction` table.

---

## 4. SQLModel & Type Safety Architecture

- **Pydantic Validation**: All models inherit from `sqlmodel.SQLModel`, giving every entity dual capability as both a database table representation (`table=True`) and a validated Pydantic serialization schema.
- **JSON Column Serialization**: Complex structures (e.g., `exception_record.evidence`, `proposal.actions`, `proposal.citations`, `audit_event.before`, `audit_event.after`) use native JSON serialization with SQLAlchemy `JSON` types, providing schema flexibility while preserving relational querying capabilities.
- **Check Constraints**: Database-level `CHECK` constraints prevent invalid state transitions at the engine level (e.g., `check_proposal_confidence_range` enforcing $0.0 \le \text{confidence} \le 1.0$, `check_shift_end_after_start` enforcing $\text{end} > \text{start}$).
