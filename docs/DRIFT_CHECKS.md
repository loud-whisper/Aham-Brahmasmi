# Workspace drift checks

`scripts/verify_workspace.py`, `aham.py check`, and `aham.py start` reject
workspace inventory drift. New workspaces include `INDEX.json`:

```json
{
  "format": "aham-brahmasmi-workspace-index",
  "version": 1,
  "files": ["BRAIN.json", "INDEX.json", "README.md", "MEMORY.md", "TODO.md", "LESSONS.md"],
  "projects": [],
  "startup_budget_bytes": 65536
}
```

`files` lists every top-level regular file, including hidden instruction files.
The only exceptions are Git metadata: `.git`, `.gitignore`, and `.gitattributes`.
This conservative inventory avoids guessing which filenames contain instructions
or state. Listed files must exist; entries use single relative names. Duplicate
names, case/Unicode collisions, traversal, symlinks, and reparse points fail.

`projects` lists folder names directly under `projects/`. Each folder must contain
a regular `PROJECT.md` record. For example, `"projects": ["demo"]` requires
`projects/demo/PROJECT.md`. A listed folder must exist. Existing ledger-managed
`projects/prj_*.md` files and `state/projects.json` retain their stable identities;
the folder inventory does not replace that registry.

## Startup bytes

`startup_budget_bytes` is a positive integer. Validation fails when source bytes
exceed it; equality passes. Startup reports the total, limit, and per-source byte
counts under `startup_context` before issuing session authority on success.
Budget failures occur before session issuance or the writer self-test.

The counted source set is:

- the required startup phases' `sources` in `core/startup.json`;
- the selected runtime profile, with the unknown profile as fallback;
- all top-level files listed in the workspace index, including the index itself;
- the rendered runtime bridge and its native managed instruction block, if any.

File sizes count actual bytes on disk. Generated text counts its UTF-8 encoding.
Nothing is silently truncated to obtain a pass. Project-specific records, optional
skills, and semantic retrieval remain on-demand context and use their existing
budgets. Runtime conversation history is outside this source inventory. Startup
diagnostic JSON is also separate; `start --compact` retains its existing 8192-byte
output limit. These are byte limits, not token estimates.

The standalone verifier and doctor use the unknown profile by default. To check a
specific runtime's source budget:

```sh
python3 scripts/verify_workspace.py --workspace WORKSPACE --runtime codex
```

Foundation validation checks the shipped workspace template against every built-in
runtime profile, so growth in shared startup sources also fails CI.

## Existing workspaces

A workspace without `INDEX.json` now fails validation with a migration hint.
Review `templates/private-workspace/INDEX.json`, create the inventory in the
selected private workspace, and list its actual top-level files and project
folders. Add missing `PROJECT.md` records before checking again. Do not replace
existing workspace files or edit `BRAIN.json` identity to pass this check.
The index is included in optional Git snapshots and portable backups.

Keep transient request bundles under `state/` rather than adding them to startup
context. Move only files you have reviewed; the validator never moves or repairs
workspace content automatically.

## Installed instruction and hook drift

The portable bridge and per-tool instruction bodies come from
`templates/runtime-bridge/`. Native command-guard groups come from
`templates/command-guard/hooks.json`; command paths are rendered for the selected
local installation. Existing verified hook protocols and activation requirements
are unchanged.

```sh
python3 scripts/runtime_bridge.py install --runtime codex --workspace WORKSPACE --project PROJECT --check
python3 scripts/install_command_guard.py --runtime codex --project PROJECT --check
```

Both commands exit nonzero for missing or changed managed content and leave files
and modification times unchanged. Bridge status also checks template content.
Unrelated owner instructions and hook groups are preserved and excluded from the
managed comparison. Changing a template makes existing installations fail checks
until reviewed and refreshed. Bridge installation refreshes its managed content;
the guard installer retains its existing explicit-repair refusal for conflicting
installed guard groups. Configuration checks do not prove runtime hook activation.
