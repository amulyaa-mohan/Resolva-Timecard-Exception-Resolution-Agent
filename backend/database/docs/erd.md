# Resolva Database Entity-Relationship Diagram

```text
organizations
     1
     |
     *
 locations            (referenced by employees.location_id; no FK yet, display data)

 managers 1 ------* manager_assignments *------ 1 employees
                                                     |
             +---------------------------------------+-------------------+
             1                    1                   1                  1
             *                    *                   *                  *
     scheduled_shifts         punches          employee_notes        day_totals
             |                    |                   |
             |                    *                   *
             |            exception_punches    exception_notes
             |                    |                   |
             |                    1                   1
             +--------* exceptions *---------------------+
                            1
         +------------------+---------+-----------------+
         *                  *         1                 *
     proposals          decisions   escalations     audit_events
         1                  1
         |                  |
         *                  1
     llm_traces         corrections
```

## Cardinality summary

| Relationship | Cardinality | Delete rule | Note |
| --- | --- | --- | --- |
| organizations -> locations | 1 : N | RESTRICT | reference data |
| employees -> manager_assignments <- managers | N : M over time | RESTRICT | `valid_from` / `valid_to` give history |
| employees -> scheduled_shifts | 1 : N | RESTRICT | |
| employees -> punches | 1 : N | RESTRICT | append-only |
| employees -> employee_notes | 1 : N | RESTRICT | |
| employees -> day_totals | 1 : N | RESTRICT | one row per local work date |
| employees -> exceptions | 1 : N | RESTRICT | |
| scheduled_shifts -> exceptions | 1 : N | RESTRICT | nullable: an exception may have no shift |
| exceptions -> exception_punches -> punches | N : M | RESTRICT | the evidence a detection used |
| exceptions -> exception_notes -> employee_notes | N : M | RESTRICT | |
| exceptions -> proposals | 1 : N | RESTRICT | every draft is kept, not just the last |
| proposals -> llm_traces | 1 : N | RESTRICT | one per model call |
| exceptions -> decisions | 1 : N | RESTRICT | at most one `approve` (partial unique index) |
| decisions -> corrections | 1 : 0..1 | RESTRICT | a rejection or escalation has none |
| exceptions -> escalations | 1 : 0..1 | RESTRICT | first escalation wins |
| exceptions -> audit_events | 1 : N | RESTRICT | ordered by `seq`, hash-chained |
| decisions -> audit_events | 1 : 0..N | RESTRICT, DEFERRABLE | event and decision are written in one transaction |

## Why some links are absent

- **No `policy_packs` table.** Policy packs are versioned YAML owned by Track B (ADR-006). Rows that
  depend on a policy store `pack_id` and `version` as text, so a historical decision stays
  reconstructable without the database owning policy text.
- **No foreign key from `employees.location_id` to `locations`.** Employee rows existed before the
  table; the key is added in a later migration once deployments have backfilled their sites.
- **No link from `corrections` to `punches`.** A correction describes actions as JSON and never
  rewrites a punch; the effective timecard is computed by applying them.
