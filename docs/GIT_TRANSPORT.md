# Optional Git durable transport

Aham Brahmasmi works without Git. The private workspace files remain the required durable Brain state.

Git is an optional way to keep local version history of selected durable state. It does not require GitHub, GitLab, Bitbucket, another remote host, or even an internet connection.

## What it versions

The Git transport uses the allowlist in `core/git_transport.json`.

Included durable state currently covers:

- workspace identity and instructions;
- memory, tasks and lessons;
- project state;
- dated history;
- checkpoints and completed wrap-up records;
- the latest-checkpoint pointer;
- installed-source provenance;
- the current workspace-state schema manifest and completed migration receipts.

It deliberately does not snapshot:

- fetched third-party source trees under `external/`;
- quarantine contents;
- replaced third-party source archives;
- scanner reports;
- the temporary `state/pending_wrap_up.json` transaction;
- the temporary `state/pending_migration.json` transaction.

Those exclusions keep transient [temporary] and reproducible third-party material out of the Brain's durable Git history while retaining the schema information required to interpret a durable snapshot correctly.

## Initialize local version history

From the Aham Brahmasmi framework repository, run:

```text
python3 scripts/git_transport.py init --workspace <private-workspace>
```

This initializes Git only inside the selected private workspace. It does not configure a remote and does not push anything anywhere.

When this tool creates a new Git repository, it uses an explicit empty Git template so configured template directories cannot silently copy executable hooks into the Brain repository. Transport-created commits also disable Git hooks for that commit. The transport is intended to record durable state, not to trigger unrelated local automation.

Git requires an author name and email before it can create commits. You may configure those yourself, or supply a workspace-local identity during initialization:

```text
python3 scripts/git_transport.py init \
  --workspace <private-workspace> \
  --author-name "Your chosen name" \
  --author-email "your-address@example.com"
```

The identity is stored in that workspace's local Git configuration. The tool does not invent an identity for you.

## Save a durable snapshot

Run:

```text
python3 scripts/git_transport.py snapshot \
  --workspace <private-workspace> \
  --message "Describe the durable change"
```

The tool stages only the allowlisted durable paths and creates a local commit. It does not push the commit to a remote.

If an unrelated or excluded path is already staged, the snapshot refuses to continue rather than silently including it.

If there are no durable changes, the command exits normally without creating an empty commit.

## Check status

Run:

```text
python3 scripts/git_transport.py status --workspace <private-workspace>
```

Before initialization, status remains nonblocking and reports that Git transport is not initialized. After initialization it reports the current branch, commit, number of durable changes and number of configured remotes.

## Remote synchronization is separate

This transport intentionally stops at safe local versioning.

You may later connect the private workspace repository to any Git-compatible remote service you choose, but Aham Brahmasmi does not automatically create an account, choose a provider, add a remote, or push private state.

Provider-specific remote setup should be documented only after the relevant public upstream behavior has been verified. The core contract must continue to work without any particular hosting provider.

## Failure behavior

If Git is unavailable or a Git command fails, the private workspace files remain intact and continue to be the required durable state.

Git transport is an optional protection layer, not the only copy of memory or project state.
