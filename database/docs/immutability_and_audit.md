# Resolva Immutability & Audit Specification

In enterprise workforce management (WFM) and payroll compliance systems, auditability and tamper resistance are paramount. Labor disputes, Fair Labor Standards Act (FLSA) audits, and union arbitrations require provable provenance of when, how, and why a timecard was modified.

This document details the architectural guarantees implemented in the Resolva database.

---

## 1. Raw Punch Immutability Principle

The foundational tenet of Resolva's database design is:

$$\text{Original Punch Count} = \text{Constant} \quad (\Delta \text{Punches} = 0)$$

### Immutability Invariants:
1. **Never Update**: The application services never execute SQL `UPDATE` operations on rows in the `punch` table.
2. **Never Delete**: The application services never execute SQL `DELETE` operations on rows in the `punch` table.
3. **No Direct Punch Insertions for Fixes**: When an employee forgets to clock out, the system **does not** retroactively insert a hardware badge punch into the `punch` table.
4. **Baseline Invariant**: The demo database baseline contains exactly **398 raw punch records**. Across all 44 test scenarios (exception detection, AI proposal generation, manager approvals, and rejections), the punch count remains strictly identical:

$$\text{Count}(\text{punch}) \equiv 398$$

---

## 2. The Delta-Correction Pattern

Rather than altering raw hardware punches, Resolva employs the **Delta-Correction Pattern**.

```
[Hardware Clock] ---> PUNCH (Raw immutable punch record)
                           |
                     (Anomaly Detected)
                           v
                    EXCEPTION_RECORD
                           |
                  (AI Proposal Generated)
                           v
                        PROPOSAL
                           |
                 (Supervisor Decision: APPROVE)
                           v
                       CORRECTION (New Adjustment Record)
                           +
                      AUDIT_EVENT (Cryptographic Ledger Entry)
```

### How Corrections Function:
- When a supervisor approves a proposal to insert a missed punch or award a meal premium, a new row is added to the `correction` table.
- The `correction` table records:
  - `proposal_id`: Foreign key linking to the AI recommendation.
  - `actions`: The exact JSON delta applied (e.g., `INSERT_PUNCH` at `2026-11-05T08:00:00`, `FLAG_MEAL_PREMIUM` for 1.0 hour).
  - `applied_by`: The supervisor's manager ID (e.g., `MGR-1049`).
  - `reason_code`: Reason classification (e.g., `MANAGER_APPROVED_AI_PROPOSAL`).
  - `comment`: Free-text justification.
  - `ts`: Timestamp of approval.
- Downstream payroll calculations compute effective time as:

$$\text{Effective Time} = \text{Raw Punches} \oplus \sum \text{Corrections}$$

---

## 3. Append-Only Audit Trail (`audit_event`)

Every state mutation in the system generates an immutable event in the `audit_event` table.

### Audit Event Attributes:
| Field | Purpose | Example |
|---|---|---|
| `id` | Monotonically increasing sequence number | `42` |
| `actor` | Attributable identity of the actor | `MGR-1049`, `SYSTEM`, `RESOLVA_AI` |
| `action` | Standardized operational verb | `PROPOSAL_APPROVED`, `EXCEPTION_DISMISSED` |
| `entity_ref` | Universal target entity reference | `proposal:7`, `exception:2` |
| `before` | JSON snapshot of entity state prior to mutation | `{"status": "open"}` |
| `after` | JSON snapshot of entity state following mutation | `{"status": "resolved"}` |
| `trace_id` | Distributed correlation trace identifier | `tr-7b2a9f14` |
| `ts` | UTC timestamp of event creation | `2026-11-18T10:45:00Z` |

---

## 4. AI Reproducibility & Prompt Hashing

To ensure that AI-generated proposals can be audited and reproduced:
- Every proposal generated calculates an SHA-256 hash of the complete context dictionary provided to the model:

$$\text{prompt\_hash} = \text{SHA256}(\text{JSON}(\text{Exception} + \text{Employee} + \text{Shift} + \text{Punches} + \text{PolicyClauses}))$$

- If regulatory auditors question why an AI proposal suggested a specific adjustment, the prompt hash allows exact re-verification against the historical database state.
