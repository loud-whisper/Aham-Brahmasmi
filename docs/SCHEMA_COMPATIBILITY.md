# Workspace schema compatibility

Aham Brahmasmi separates the immutable workspace identity envelope from the mutable workspace-state schema.

## Identity envelope

`BRAIN.json` is the workspace identity envelope. Its current format is `aham-brahmasmi-workspace` and its identity-envelope version is `1`.

That version is intentionally not used as a normal migration counter. It participates in the workspace fingerprint that is recorded by durable checkpoints and immutable operation history. Rewriting the `BRAIN.json` identity-envelope version would therefore change identity semantics and could make previously committed evidence appear to belong to a different workspace.

The R1 migration runner does not rewrite `BRAIN.json`, `workspace_id`, immutable operation records, checkpoints, or user-authored durable content. An unsupported identity-envelope format/version is refused before migration mutation.

## Workspace-state schema

The mutable workspace-state schema is recorded separately in `state/schema.json`.

Current manifest:

```json
{
  "format": "aham-brahmasmi-workspace-schema",
  "version": 1
}
```

Compatibility policy:

- **Schema 0** means a valid pre-R1 workspace with no `state/schema.json` manifest. This is the only legacy schema currently supported for automatic migration.
- **Schema 1** is the current schema. New workspaces are created directly at schema 1.
- A schema version newer than the framework supports is refused without mutation. The user must use a newer compatible framework.
- Unknown/invalid manifests are refused rather than guessed or silently repaired.
- The framework does not claim compatibility with a historical schema unless an explicit tested migration path exists.

## Migration command

Run:

```bash
python3 scripts/migrate_workspace.py --workspace /path/to/workspace
```

Migration from schema 0 to schema 1 only adds the explicit schema manifest and a durable migration receipt. It does not rewrite existing durable history or user content.

A current schema-1 workspace is an idempotent no-op and reports `MIGRATION NOT NEEDED`.

## Interrupted migration and recovery

Migration is replay-safe. Before changing schema state, the runner writes `state/pending_migration.json`. Completed migrations are recorded under `state/migrations/`.

If migration is interrupted after the schema manifest is written but before completion is recorded, rerunning the same command validates the pending transaction, validates the already-written schema, writes or verifies the completion receipt, and removes the pending record. It reports `MIGRATION RECOVERED`.

The runner also supports recovery if interruption occurs after the completion receipt is written but before the pending marker is cleared.

A pending migration is bound to the workspace ID and exact supported version transition. Mismatched or malformed pending state is refused instead of being treated as success.

## Normal lifecycle gate

Normal lifecycle commands require the current workspace-state schema through the shared workspace validator. A pre-R1 schema-0 workspace is readable enough for the migration runner to validate its identity, but normal mutation is blocked until migration completes.

This avoids silently interpreting old state with new semantics while preserving the immutable identity and history established before R1.
