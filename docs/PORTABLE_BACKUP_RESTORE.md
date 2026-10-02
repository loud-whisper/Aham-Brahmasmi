# Portable export and restore

R4 adds a provider-neutral portable export of authoritative Aham workspace state. The local user-owned workspace remains the source of truth.

## What a portable export means

A portable export is an inspectable local bundle containing a deterministic manifest plus copied durable record/artifact files. It is independent of any semantic-memory provider, Git remote, or hosting service.

A successful export is **not** evidence of replicated backup. It proves only that a local portable copy was created and its payload matched the manifest. Replication to another disk, machine, cloud service, or remote host is a separate action and must be described separately.

## Included state

The export contract is `core/portable_backup.json`. It includes workspace identity, human-readable memory/tasks/lessons, project/history artifacts, immutable operation records, state-store metadata, checkpoints, wrap-up receipts, project indexes/heads, installed-source provenance, schema state, and completed migration receipts.

The manifest records every included file with its relative path, class (`record` or `artifact`), byte size, and SHA-256 digest. The manifest contains no export timestamp or machine-local source path, so the same committed state produces the same manifest.

## Excluded state

The portable bundle deliberately excludes restore-local or reproducible/transient material, including:

- `state/session_authority.json`;
- writer locks and pending checkpoint/wrap-up/migration transactions;
- fetched third-party trees under `external/`;
- quarantine, replaced-source archives, and scan reports;
- `.git/` metadata.

Session authority is not portable authority. A restore issues a fresh local bootstrap session bound to the restored workspace and current committed revision instead of copying the source session token.

If a supported Aham mutation or migration is still pending, export refuses to proceed. Resolve/recover the operation first so the export represents one committed durable revision.

## Export

```text
python3 scripts/portable_backup.py export \
  --workspace <private-workspace> \
  --output <new-export-directory>
```

The output directory must not already exist and must be outside the source workspace. The tool writes:

```text
<export>/manifest.json
<export>/payload/...
```

Export acquires the same authoritative workspace writer lock used by durable mutations and keeps it while the manifest is built, files are copied, the bundle is verified, and the completed export is published. This prevents supported Aham writers from interleaving a mutation with the snapshot.

It re-verifies every exported payload digest before publishing the bundle.

## Inspect a workspace manifest

```text
python3 scripts/portable_backup.py manifest \
  --workspace <private-workspace> \
  --json
```

This is useful for comparing a source and restored workspace without relying on semantic-memory state or Git metadata.

## Restore

Restore only into a missing or empty clean location:

```text
python3 scripts/portable_backup.py restore \
  --input <export-directory> \
  --workspace <clean-destination>
```

Before the final destination is created, restore validates the manifest structure, requires the payload file set to match exactly, verifies every SHA-256 digest/size, reconstructs the workspace in a temporary sibling directory, and compares the restored portable manifest with the source manifest. It then issues fresh session authority and publishes the clean workspace.

A bundle whose payload no longer matches its manifest, or whose payload is incomplete, is refused without leaving a partial new destination. SHA-256 here provides an integrity check against accidental or payload-only modification, not authenticity: a party able to alter both the manifest and payload can produce a new self-consistent bundle. A non-empty destination is never overwritten.

## Semantic-memory independence

Semantic-memory providers remain optional recall integrations. Portable export/restore neither calls nor requires them. Provider configuration present in `BRAIN.json` remains part of the user's workspace configuration, but provider caches or service-side state are not authoritative restore inputs.

## Backup terminology

- **Durable local workspace save:** authoritative state exists in the user's workspace.
- **Portable export:** a verified local copy represented by `manifest.json` plus payload files.
- **Replicated backup:** at least one additional independently stored copy exists on another storage target/location.

Creating an export does not by itself establish a replicated backup.
