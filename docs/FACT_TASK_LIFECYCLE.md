# Fact and task lifecycle

R2 adds structured lifecycle semantics without replacing the existing immutable operation ledger or the human-readable Markdown projections.

## Authority and storage

The immutable operation ledger remains authoritative. `scripts/record_lifecycle.py` reconstructs the current fact/task view by replaying committed `wrap_up` and `record_lifecycle` operations in revision order. There is no separately mutable fact/task database.

Lifecycle mutations use the existing workspace writer lock and session mutation authority. Degraded/read-only sessions therefore cannot alter lifecycle state.

## Stable records

Facts derived from committed wrap-up operations receive deterministic IDs of the form `fact_<32 hex>`. Tasks receive `task_<32 hex>`. IDs are derived from the committed operation identity, revision, item index, and content, so repeated reconstruction yields the same identities.

Each record retains provenance containing its originating operation, revision, source type, and content digest. Explicitly asserted facts may also carry a source label.

## Fact states

A fact starts as `active`.

- `fact_supersede` preserves the original fact as `superseded`, creates a new active fact, and links both directions with `superseded_by` / `supersedes`.
- `fact_retract` preserves the fact and marks it `retracted`.
- `fact_assert` creates a distinct fact. `conflicts_with` links contradictory or competing facts explicitly rather than flattening them into a single statement.

Lifecycle events retain the operation/revision and transition reason.

## Task states

A task starts as `open`.

- `task_complete` transitions it to `completed`.
- `task_cancel` transitions it to `cancelled`.

Terminal tasks are preserved. A second terminal transition is rejected without committing a new revision.

## Idempotency and receipts

Every lifecycle mutation has an `operation_id` and canonical payload digest. An exact retry reuses the committed receipt. Reusing the same operation ID with different content is rejected.

The `status` command reconstructs lifecycle state from the immutable ledger and verifies the committed receipt before reporting `independently_verified: true`.

## Compatibility

Existing wrap-up Markdown remains intact and continues to be the human-readable projection. R2 derives structured lifecycle identities from already committed wrap-up records, so historical user content does not need to be rewritten or migrated solely to gain lifecycle semantics.
