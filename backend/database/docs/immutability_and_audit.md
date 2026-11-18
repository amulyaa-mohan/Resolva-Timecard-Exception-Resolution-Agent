# Resolva Immutability and Audit Specification

Every claim here is enforced by the database, not only by the application. The enforcement column
names the exact mechanism, so a reviewer can check it.

## 1. Raw punch immutability

A punch is what a device recorded. Resolva never edits one.

### Invariants

| Invariant | Enforcement |
| --- | --- |
| A punch is never updated | `punches_append_only` trigger (BEFORE UPDATE) |
| A punch is never deleted | `punches_append_only` trigger (BEFORE DELETE) |
| A punch table is never truncated | `punches_no_truncate` trigger (BEFORE TRUNCATE) |
| An employee cannot be deleted out from under their punches | `ON DELETE RESTRICT` |
| The same source event cannot be stored twice | `UNIQUE (source, source_event_id)` |
| The instant is unambiguous | `timestamptz`; the employee's timezone gives the local date |

A re-import of the same file therefore inserts nothing and changes nothing.

## 2. The delta-correction pattern

```text
punches (raw, immutable)
        +
corrections (approved actions, append-only)
        =
effective timecard  (computed; GET /exceptions/{id}/timecard)
```

### How corrections work

1. A manager approves actions; the validator re-checks them against fresh evidence first.
2. One row is written to `corrections`, linked 1:1 to the `decisions` row that authorised it.
3. Nothing in `punches` changes.
4. `exceptions.correction_revision` is incremented, which changes the evidence hash and makes every
   earlier proposal stale.
5. Detection applies approved corrections on top of the raw punches, so a resolved exception is not
   raised again.

A reversal would be another correction row, never a delete.

## 3. Append-only audit trail

Six tables are append-only, each with its own trigger: `punches`, `decisions`, `corrections`,
`audit_events`, `proposals`, `llm_traces`. Attempting an UPDATE or DELETE raises
`<table> is append-only`.

### Event attributes

| Column | Purpose |
| --- | --- |
| `seq` | total order |
| `occurred_at` | when it happened, UTC |
| `actor_type` / `actor_id` | `manager` (a credential), `system` (detection, validator), `ai` (provider and model) |
| `event_type` | what happened |
| `exception_id` / `decision_id` | what it happened to |
| `payload_json` | the evidence version, policy, rule version, checks and the totals used |
| `prev_hash` / `hash` | the chain |

### Why a hash chain as well as triggers

A trigger stops the application and any ordinary client. It does not stop someone with rights to
drop the trigger. Each event hashes its own fields plus the previous event's digest, so any later
edit, deletion or reordering breaks the chain and `verify_chain` returns false. A test drops the
trigger, edits a row and asserts the chain fails.

### What is always recorded

| Event | Written when |
| --- | --- |
| `EXCEPTION_DETECTED` | detection creates an exception |
| `PROPOSAL_GENERATED` | the AI drafts a correction (actor `ai`, with the trace id) |
| `APPROVAL_BLOCKED` | an approval failed validation; committed even though the request returns 422 |
| `DECISION_APPROVED` | with the actions, the checks and the totals used |
| `DECISION_REJECTED` / `DECISION_ESCALATED` | with the manager's reason |

A blocked approval is deliberately audited: an attempt to approve something unsafe is exactly what
a reviewer needs to see.

## 4. AI reproducibility

`proposals` stores the draft, the gate results and the validation; `llm_traces` stores the provider,
model, prompt version, prompt hash, retrieved clause ids, raw outputs, parse errors, attempts and
latency. Together with the `evidence_version` and the policy `pack@version` on the proposal row,
a past decision can be reconstructed: the same evidence, the same policy text and the same prompt.

Model output is never trusted on its own. A proposal only becomes approvable if the deterministic
validator passes it, and approving re-runs that validator against freshly read evidence.

## 5. The retention boundary

Immutability and retention pull in opposite directions. Model text can quote an employee's note, so
a retention policy must be able to remove it; audit evidence must not be removable at all. They are
therefore split: `llm_traces` (append-only) keeps provider, model, prompt version and hash,
retrieved clauses, attempts, latency and error; `llm_raw_outputs` (not append-only) keeps the raw
replies. Purging leaves the trace, proposal, validation and audit event intact, so a past decision
stays provable.

## 6. What is deliberately mutable

| Table | Why |
| --- | --- |
| `exceptions.status`, `correction_revision` | lifecycle state; every transition is audited |
| `day_totals` | derived, recomputed by detection and after an approval |
| `llm_raw_outputs` | retention, as above |
| reference tables | people and sites change; history is not kept here |
