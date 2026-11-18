# Resolva ER design (DB-01 draft, PostgreSQL 15+)

Authoritative DDL: `backend/database/migrations/0001_initial.sql`. Python access: `backend/app/attendance/postgres.py`.
Status: REVIEW. Built by Track A (C V Jayanth) on 2026-11-18. Database-team review is pending (Soumya's work is not yet pushed).

```text
organizations 1─* locations ←(by id, no FK yet)─ employees        [display reference data]

managers 1─* manager_assignments *─1 employees 1─* scheduled_shifts
                                        │ 1─* punches          (raw, append-only)
                                        │ 1─* employee_notes
                                        │ 1─* day_totals       (trusted per-day hours)
                                        └ 1─* exceptions ─* exception_punches / exception_notes
                                                  │ 1─* decisions 1─0..1 corrections   (append-only)
                                                  └ 1─* audit_events                    (append-only, hash chain)
```

| Rule | How it is enforced |
| --- | --- |
| Instants stored in UTC with the original zone known | `timestamptz` everywhere; `employees.timezone` (IANA) defines local work dates |
| Raw punches never change | Triggers reject UPDATE, DELETE and TRUNCATE; corrections are separate rows |
| Re-imports cannot duplicate punches | `UNIQUE (source, source_event_id)` |
| One live exception per employee/date/code | Partial unique index on `status IN ('open','escalated')` |
| One approval per exception | Partial unique index `decisions_one_approval` |
| Retries are safe | `decisions.idempotency_key UNIQUE` plus stored response |
| Stale approvals rejected | `exceptions.correction_revision` bumped in the approval transaction; evidence hash recomputed |
| Audit is append-only and tamper-evident | Triggers on `audit_events`, SHA-256 `prev_hash`/`hash` chain |
| No cascading deletes of evidence | Every foreign key is `ON DELETE RESTRICT` |
| Access follows assignments over time | `manager_assignments.valid_from/valid_to`; loads check the current window |
| Policy is reconstructable | Decisions and audit payloads record `pack@version`, rule version and totals used |

Concurrency: every writing transaction takes one advisory lock. It also locks the exception row (`FOR UPDATE`).
Together these serialize decisions and keep the audit chain linear (a 4-thread race test leaves exactly one approval).

Migrations: numbered `NNNN_name.sql` files applied in order by `apply_migrations` (`scripts/migrate_postgres.py`).
Each is recorded in `schema_migrations` with a checksum. Editing an applied file is refused; add a new migration instead.
Rollback: none automated. Write a new forward migration. Never drop audit or punch data.

Not modelled yet: the policy pack table (packs stay versioned YAML, referenced by `pack@version`),
`proposals` / `llm_traces` (Track B, next migration), escalation records and bulk decisions.

## Migration history

| File | Adds |
| --- | --- |
| `0001_initial.sql` | People, raw attendance, exceptions, decisions, corrections, audit, day totals |
| `0002_proposals_escalations.sql` | `proposals`, `llm_traces`, `escalations`; manager `escalate` decisions |
| `0003_organization_and_display_fields.sql` | `organizations`, `locations`, employee `full_name` / `job_title` / `pay_type` |

Migration 0003 comes from the database branch's design (`48b2a1a`): the rules need only ids, but a
manager reviewing an exception needs to see who and where. These columns are **display only**. No
rule, validator or authorization check reads them, and detection works with every one of them null
(tested). `employees.location_id` already held these ids; the foreign key to `locations` waits for a
later migration, once deployments have backfilled their sites.

The database branch (`origin/database`, `48b2a1a`) is not merged. It targets SQLite via SQLModel,
is based on the pre-reorganisation layout, uses naive timestamps, enforces no immutability triggers
and cascade-deletes evidence. Review notes were sent to its author; the reconciliation plan is to
keep this migration history and fold in that branch's documentation and reference tables.
