# Manual setup

This page is for people who prefer to inspect and create everything themselves.

## What gets created

Aham Brahmasmi keeps the public framework separate from your private workspace.

A new private workspace contains:

```text
BRAIN.json
MEMORY.md
TODO.md
LESSONS.md
README.md
external/
history/
projects/
state/
  checkpoints/
  wrapups/
  quarantine/
  scan_reports/
  replaced_sources/
  installed_sources.json
```

`BRAIN.json` identifies the workspace format and contains a unique `workspace_id` so a checkpoint from one Brain cannot be mistaken for a checkpoint from another. The Markdown files begin empty except for short instructions about what belongs in them.

## Create it with the included setup tool

From the Aham Brahmasmi repository, run:

```text
python3 scripts/setup_workspace.py --workspace <path>
```

Choose any writable location outside this repository. The setup tool will not overwrite an existing non-empty directory. It also creates a new random workspace identity.

Then verify it:

```text
python3 scripts/verify_workspace.py --workspace <path>
```

A successful verification exits with status 0 and prints `WORKSPACE VERIFIED`.

## Create it without Python

Copy the contents of `templates/private-workspace/` into a new private folder outside this repository. Preserve the same filenames and folders.

The template deliberately leaves `workspace_id` as `null`. Replace it with a unique 32-character lowercase hexadecimal value before using the workspace. A UUID v4 with its hyphens removed is suitable. Do not reuse an ID from another workspace.

Then confirm:

- `BRAIN.json` is valid JSON and has a unique `workspace_id`;
- `MEMORY.md`, `TODO.md`, `LESSONS.md`, and `README.md` exist;
- `external/`, `history/`, `projects/`, `state/checkpoints/`, `state/wrapups/`, `state/quarantine/`, `state/scan_reports/`, and `state/replaced_sources/` exist;
- `state/installed_sources.json` uses the `aham-brahmasmi-installed-sources` format;
- none of those private files were placed inside the public Aham Brahmasmi repository.

## Verify startup state

After the workspace verifies, the model-neutral startup executable can inspect the same durable state regardless of which runtime is currently using it:

```text
python3 scripts/startup.py --workspace <path> --runtime unknown --mode regular
```

Replace `unknown` with `claude`, `gemini`, `codex`, or `local` when that profile describes the current runtime. A different runtime name safely uses the unknown-runtime fallback.

Runtime profiles do not grant permissions. Add only capabilities that the active runtime has actually verified, for example:

```text
python3 scripts/startup.py \
  --workspace <path> \
  --runtime local \
  --mode regular \
  --capability read_files \
  --capability write_files \
  --capability run_commands
```

The recognized capability names are:

- `read_files`
- `write_files`
- `run_commands`
- `git`
- `network`
- `skill_loader`
- `semantic_memory`

Omitting a capability means the startup report does not claim it exists. Basic startup does not require a native skill loader or semantic memory.

Quick mode requires explicit confirmation that current context is already loaded and verified:

```text
python3 scripts/startup.py --workspace <path> --runtime unknown --mode quick --context-loaded
```

Use `--json` when a machine-readable ready report is preferable.

See `docs/RUNTIME_PORTABILITY.md` for the full behavior and limitations.

## What each place is for

- `MEMORY.md`: long-lived facts and preferences worth carrying into future sessions.
- `TODO.md`: unfinished work and next actions.
- `LESSONS.md`: reusable mistakes, fixes and discoveries.
- `projects/`: project-specific durable context.
- `history/`: dated summaries of meaningful work.
- `state/checkpoints/`: recovery points for interrupted work.
- `state/wrapups/`: completed wrap-up transaction records.
- `state/pending_wrap_up.json`: exists only while a wrap-up needs to finish or recover.
- `external/`: reviewed third-party sources that have passed the configured scanner.
- `state/quarantine/`: newly fetched or changed external sources before activation.
- `state/scan_reports/`: scanner results retained for later inspection.
- `state/replaced_sources/`: previous active copies preserved during an explicit replacement.
- `state/installed_sources.json`: provenance [where it came from] and scan record for active external sources.

The lifecycle commands are documented in `docs/LIFECYCLE.md`. The external-source safety flow is documented in `docs/THIRD_PARTY_POLICY.md`.

## Optional external sources

The basic workspace does not require Git, MemPalace, external skills, a particular model, or a particular CLI.

To see which external sources have already been reviewed:

```text
python3 scripts/external_sources.py list
```

To fetch the approved default set through quarantine and scanning:

```text
python3 scripts/external_sources.py install-defaults --workspace <path>
```

To fetch one approved installer source:

```text
python3 scripts/external_sources.py install <source-id> --workspace <path>
```

Fetching a source is not the same as granting it runtime-specific hooks, permissions, or automatic execution. Runtime activation remains a separate step.
