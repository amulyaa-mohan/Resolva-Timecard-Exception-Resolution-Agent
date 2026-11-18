# Resolva Database Architecture

## 1. Architectural overview

Four layers, each with a different trust level:

```text
Telemetry        punches, scheduled_shifts, employee_notes      raw, append-only
Reference        organizations, locations, managers, employees,  slow-changing
                 manager_assignments
Derived          exceptions, day_totals                          recomputed by detection
Decision record  proposals, llm_traces, decisions, corrections,  append-only, audited
                 escalations, audit_events
```

Only the decision layer records what a human chose. The derived layer can always be recomputed
from telemetry plus approved corrections, which is what the detection job does after every import.

## 2. Table categorisation

| Category | Tables | Written by |
| --- | --- | --- |
| Reference | `organizations`, `locations`, `managers`, `employees`, `manager_assignments` | provisioning |
| Telemetry | `punches`, `scheduled_shifts`, `employee_notes` | import (append-only) |
| Derived | `exceptions`, `exception_punches`, `exception_notes`, `day_totals` | detection |
| AI | `proposals`, `llm_traces` | the proposal endpoint (append-only) |
| Decision | `decisions`, `corrections`, `escalations` | manager actions (append-only) |
| Ledger | `audit_events` | every layer above (append-only, hash-chained) |

## 3. PostgreSQL concurrency strategy

A decision must be atomic across five tables, and two managers may act at once. Every writing
transaction:

1. takes `pg_advisory_xact_lock`, which serialises writers and keeps the audit chain linear;
2. selects the exception `FOR UPDATE`, so its correction revision cannot move underneath it;
3. re-reads the weekly and quarterly totals *inside* the transaction, so an approval is never
   validated against numbers read earlier;
4. writes the decision, the correction and the audit event, then bumps `correction_revision`.

Any failure rolls back all of it. A conditional `UPDATE ... WHERE correction_revision = ?` detects a
revision that moved despite the lock, and the partial unique index `decisions_one_approval`
guarantees at most one approval per exception even if every other guard were removed.

## 4. Type safety without a second model layer

The Pydantic contracts in `backend/app/core/contracts.py` are the only type definition. The database
layer builds those models directly from rows, so the database and the API cannot disagree about a
field. Database-level CHECK constraints repeat the enums (punch type, source, severity, status,
outcome) so that an unexpected value is rejected even if it arrives through another client.

Deliberately not used:

- **An ORM.** A SQLModel or SQLAlchemy model set would be a second definition of the same types,
  free to drift from the contracts; the area guide forbids a parallel model layer.
- **Cascade deletes.** Every foreign key is `ON DELETE RESTRICT`: evidence must never disappear
  because a parent row was removed.
- **Database-generated surrogate keys.** Identifiers are the business ids the contracts carry
  (`E-001`, `EX-...`), so a row can be matched to an imported record and to an API response.
