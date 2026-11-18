# Resolva Database Migrations

This directory contains database DDL migration scripts and migration management utilities for the **Resolva — Timecard Exception Resolution Agent**.

---

## Migration Files

| Migration | Type | Description |
|---|---|---|
| `001_initial_schema.sql` | SQL DDL | Establishes the complete 11-table schema, 53 indexes, unique constraints, and foreign key relations for SQLite. |
| `apply_migrations.py` | Python Script | CLI utility to execute migrations sequentially against any target SQLite database with `PRAGMA foreign_keys = ON`. |

---

## Applying Migrations

### Default Target (`backend/shiftsense.db`)
```bash
python migrations/apply_migrations.py
```

### Custom Target Database Path
```bash
python migrations/apply_migrations.py /path/to/custom_database.db
```

---

## SQLite Migration Guidelines

1. **Foreign Keys**: SQLite disables foreign keys by default per connection. All migrations and application connections must explicitly run `PRAGMA foreign_keys = ON;`.
2. **Deterministic Schema**: Tables use strict type affinities, `CHECK` constraints for ranges (`confidence BETWEEN 0.0 AND 1.0`, `end > start`, `planned_break_min >= 0`), and unique index constraints.
3. **Non-Destructive Evolution**: Future migrations should introduce additive changes or use temporary table copy patterns (`BEGIN TRANSACTION; CREATE TABLE new_...; INSERT INTO new_... SELECT ...; DROP TABLE old_...; ALTER TABLE new_... RENAME TO old_...; COMMIT;`).
