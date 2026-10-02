# Using Aham with your assistant

Use a Python interpreter available on your supported system. In examples, replace
`PYTHON` with that interpreter, `WORKSPACE` with your private workspace, and
`PROJECT_ID` with the stable project ID reported by your workspace. Run commands
from the framework folder. Existing scripts remain compatible entry points.

## Using Aham with a tool that is not listed

An assistant needs file and command tools to operate Aham directly. Runtime names
select instruction files; they do not grant writes. The workspace owner chooses
which runtime names to trust:

```text
PYTHON aham.py trust-runtime my-assistant --workspace WORKSPACE --confirm my-assistant
PYTHON aham.py start --workspace WORKSPACE --runtime my-assistant --mode regular --capability read_files --capability write_files --capability run_commands --compact
```

Supply capabilities only after verifying them in this session. Startup checks the
workspace and performs a transient controller write/read/cleanup probe. It grants
writes only when all required checks pass, returns a session ID, and preserves
read-only operation otherwise. The probe proves the controller's filesystem
writer works; it does not discover the assistant's tools or prove that an assistant
will follow instructions. Use the returned `--session-id` for saves and wrap-ups.

Trust is an explicit owner command. Assistants must obtain the owner's authorization
before invoking it. The repeated name records intent, not authenticated human
identity. These controls are application rules, not a sandbox against a process
with the same filesystem permissions. See the existing session authority contract.

You can also choose trust during a new setup with repeatable
`aham.py setup --workspace WORKSPACE --trust-runtime my-assistant`. No vendor is
trusted automatically. Trust is recorded in the immutable operation ledger;
`state/runtime_trust.json` is a disposable view and cannot grant authority.

```text
PYTHON aham.py runtimes --workspace WORKSPACE
PYTHON aham.py revoke-runtime my-assistant --workspace WORKSPACE --confirm my-assistant
PYTHON aham.py connect --runtime my-assistant --workspace WORKSPACE --project PROJECT
```

Revocation prevents subsequent mutation and startup writes. Owner controls replace
the active session; restart the assistant before its next write. Unlisted runtimes
use a manual bridge: read `.aham/runtime.md`. Known instruction profiles preserve
unrelated instructions. Local paths stay in ignored `.aham/runtime.json`.

If a trust command commits but its cache write fails, the recorded choice remains
authoritative. Repair the view with
`PYTHON scripts/runtime_trust.py repair --workspace WORKSPACE --session-id SESSION_ID`
under an authorized current session; do not reapprove merely to repair a cache.
Recover pending checkpoints or wrap-ups before changing or repairing trust.

## Existing workspaces and migration

Run `aham.py check`. If schema migration is required, back up your workspace and
run the R1 migration runner through `aham.py migrate --workspace WORKSPACE`, then
check again. Current schema version remains 1: the new runtime-control records are
additive. The runner preserves workspace identity and history; it never converts
the old vendor profile list into trust. An existing workspace without trust records
defaults to no trusted runtime. The owner must explicitly trust their chosen names
and restart. Existing vendor-issued sessions cannot bypass this requirement.

If legacy pending work prevents changing trust, the owner can run
`aham.py recover-access --workspace WORKSPACE --confirm WORKSPACE_ID`, using the
exact workspace_id from BRAIN.json. This issues a held session that allows recovery
only. Pass its `--session-id` to the pending save/wrap-up recovery command. It
cannot create new work or change trust. Recover first, then trust and start normally.
Assistants must obtain owner authorization before invoking this control.

## Using Aham with a chat website

A chat website cannot run local setup or write your workspace. A local user or
assistant with command tools first sets up the private workspace and connects a
project. Then the user exports context:

```text
PYTHON aham.py context --workspace WORKSPACE --project-id PROJECT_ID --for-chat
```

The output is a bounded JSON packet with a `wrapup_template`. Inspect it before
pasting it into a website: it contains selected private records. Exporting never
uploads anything. The default budget is 12,000 bytes; `--max-bytes` accepts
2,048–65,536, and reports an error when required metadata cannot fit.

Ask the chat model to return the template filled with evidence-supported facts,
unfinished work, lessons, updates, history and checkpoint. Preserve workspace,
project, base revision and operation ID. Return one JSON object, optionally between
the exact lines `BEGIN AHAM WRAPUP` and `END AHAM WRAPUP`. Artifact paths and
authority changes are not accepted from chat responses.

Save the response as a UTF-8 file, inspect it, and import under your current
user-held writer session:

```text
PYTHON aham.py import-wrapup RESPONSE_FILE --workspace WORKSPACE --session-id SESSION_ID
```

The canonical wrap-up writer commits accepted content and prints `WRAP UP VERIFIED`.
Malformed, oversized, foreign, stale or unauthorized responses are rejected before
workspace mutation. A repeated identical import reuses its verified receipt;
changed content, scope or base revision under the same operation ID refuses.
Export fresh context if another writer advanced the workspace before a new import.
Chat prose has no direct writer authority. Optional recall remains untrusted data.

## Save, recover, and diagnose

`aham.py save`, `wrap-up`, `resume`, `memory`, `skills`, `backup`, `restore`, and
`check` delegate to the existing controllers. Run any command with `--help` for
required arguments. Saves require actual `CHECKPOINT VERIFIED` output; wrap-ups
require `WRAP UP VERIFIED`. Pending operations need their reported recovery command
and active session ID. Recovery guidance uses the running Python interpreter.

Use `aham.py start --compact` for small assistant instructions and `start --json`
for full diagnostics. The tested bridge plus compact startup budget is 12 KiB.
If compact metadata is too large, use full diagnostics. Degraded mode stays
read-only, including for a trusted runtime.
