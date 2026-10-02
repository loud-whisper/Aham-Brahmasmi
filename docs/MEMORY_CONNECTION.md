# Optional recall

Aham's committed records remain authoritative. Recall never grants permissions
or changes the status of a fact or task.

## Offline keyword recall

Use the standard-library provider without installing anything:

```sh
python3 scripts/semantic_memory.py configure --workspace <workspace> --provider lite
python3 scripts/semantic_memory.py search --workspace <workspace> --project-id <project-id> --query "pending proposal"
```

Keyword recall returns active facts, open tasks, lessons and project updates from
the selected project's committed ledger. It does not perform semantic matching.
Ambiguous multi-project facts, tasks and lessons are excluded from project recall.
An explicit `--all-scopes` request permits broad recall and prints a warning.

## MemPalace

```sh
python3 scripts/semantic_memory.py setup --workspace <workspace>
python3 scripts/semantic_memory.py configure --workspace <workspace> --provider mempalace
python3 scripts/semantic_memory.py connect-project --workspace <workspace> --project-id <project-id>
python3 scripts/semantic_memory.py search --workspace <workspace> --project-id <project-id> --query "pending proposal"
```

Setup detects the CLI on PATH and presents upstream installation options. The
user chooses and performs an installation separately. The setup skill installed
by `npx skills add` is not the CLI. A package version does not establish identity
with the reviewed Git commit. Aham does not install packages, provider hooks,
background miners or native loaders.

Project wings default to stable project IDs. `connect-project --wing <wing>`
sets a custom lowercase wing; another project cannot reuse it. A configured
`--wing` remains a compatibility default for unverified recall without a project
ID. It cannot authenticate results against a project catalog.

Scoped wake-up uses wing-filtered search because upstream native wake-up also
includes global identity. Provider text is JSON escaped inside an untrusted-data
block. Exact record stamps are checked against a single committed ledger snapshot:
`matched_current` means the returned bytes match a current committed record,
not that the underlying statement is true. Superseded/retracted facts and
completed/cancelled tasks are stale. Forged bindings remain unverified; known
foreign-project record stamps are omitted. Unstamped provider prose cannot be
authenticated or reliably assigned to a project and stays unverified.

## Opt-in indexing

```sh
python3 scripts/semantic_memory.py enable-indexing --workspace <workspace> --project-id <project-id>
python3 scripts/semantic_memory.py index --workspace <workspace> --project-id <project-id>
python3 scripts/semantic_memory.py status --workspace <workspace> --json
python3 scripts/semantic_memory.py disable-indexing --workspace <workspace> --project-id <project-id>
```

Omit the project ID on enable/disable-indexing to change the workspace default.
Configuration and indexing need current writer authority; use `--session-id`
when a session presents its authority explicitly. Edited BRAIN cache fields and
legacy configuration cannot opt in. Reconfiguring the provider resets indexing
progress and per-project opt-in overrides.

After a new committed wrap-up, opted-in projects are indexed automatically.
Explicit indexing also supports revisions made by record-lifecycle commands.
A reused wrap-up receipt does not repeat indexing. Failures never invalidate the
committed wrap-up receipt.

Indexing exports verified scoped records, including inactive statuses, under
stable record paths in `state/recall_staging/<project-id>/corpus/`. It calls
`mine ... --mode projects --wing ... --direct`, with a finite timeout and output
limit. Only generated staging files are cleaned; occupied or aliased paths refuse.
Staging is excluded from Git snapshots and portable exports. Abrupt termination
can retain files that must be inspected before retrying. Do not configure an
independent provider sync job to prune these intentionally transient source files.

Progress advances only when the synchronous summary reports every staged file
processed and zero skips. Status compares content revisions with recorded command
progress. This is provider-reported evidence, not proof of complete or durable
provider storage. Hub forwarding, incompatible summaries, skips and timeouts
preserve lag. Lite recall reads the current ledger directly and needs no index.

Connection changes and index progress have immutable `memory_control` receipts.
BRAIN's optional field is a derived compatibility view. If a cache write fails
after commitment, `repair --workspace <workspace>` rematerializes it without
creating a new approval or operation. `disable` removes connection configuration
without deleting provider data.

## Upstream MCP

MemPalace documents its own [MCP integration](https://github.com/MemPalace/mempalace/blob/f8b9ed1507888cab47c7c7e1d90755f89e0353c4/README.md).
A runtime may connect to it directly under the user's authorization. Its write
tools write provider state; they cannot write Aham's canonical records or bypass
Aham session authority. This milestone adds no MCP bridge.

See [source review evidence](S4_SOURCE_REVIEW_EVIDENCE.md) and
[test design](S4_TEST_DESIGN.md). Whole-tree scanner FAIL remains a source
activation block; CLI interface review does not waive it.
