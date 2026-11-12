# If something goes wrong

You do not need to diagnose the architecture yourself. The quickest first check is:

```text
PYTHON aham.py check --workspace <your-private-workspace>
```

If you are also working inside a project that has an Aham Brahmasmi bridge, add:

```text
--project <your-project-folder>
```

`PYTHON` means the interpreter actually available in your session. The doctor checks
your chosen workspace without repairing it. Its readiness result is about durable
state; `aham.py start` separately decides runtime write authority. The doctor
separates required problems from optional features. Missing optional Git history, MemPalace or external skills does not make the basic Brain unusable.

## `WORKSPACE VERIFICATION FAILED`

What it means: the folder you pointed at is missing required Brain files, contains an invalid `BRAIN.json`, or is in an unsafe location.

What to do:

1. Confirm you selected the private Brain workspace rather than the public Aham Brahmasmi framework folder.
2. Run:

```text
python3 scripts/verify_workspace.py --workspace <your-private-workspace>
```

3. Follow the specific missing-file or identity message. Do not overwrite a different non-empty folder to make the warning disappear.

If you have never created a private workspace, go back to `START_HERE.md` and use the normal setup path.

## `BRAIN STARTUP BLOCKED`

The startup report prints the reason.

A common reason is an unfinished checkpoint or wrap-up. `aham.py check` reports
the appropriate recovery command. For a checkpoint use `aham.py save --recover-pending`
with your current session ID. In that case, new unrelated work is intentionally blocked until the durable state is made consistent again.

Run:

```text
PYTHON aham.py wrap-up --workspace <your-private-workspace> --recover-pending --session-id SESSION_ID
```

If the pending transaction recorded a project Git state, provide the same project with `--repo <project-folder>` so it can be verified.

Quick mode no longer blocks startup. It starts read-only; see the next section if a save or wrap-up is refused.

## A save or wrap-up is refused

Read the message; it names the cause.

- **"Quick sessions are read-only"**: run `PYTHON aham.py start` again with `--mode regular`, then use the new session ID.
- **"until the startup context is confirmed as read"**: the assistant has not confirmed its reading. It should run `PYTHON aham.py context --startup --workspace <your-private-workspace>`, read each part with `--part N`, then run `PYTHON aham.py confirm-context` with every part's `part_sha256` until it prints `CONTEXT CONFIRMED`.
- **`CONTEXT CHECK COULD NOT RUN`**: the workspace or a standing file changed after the session started. Run `start` again and read the new packet.
- **"is N bytes; the cap is M"**: one entry is too long. Shorten it or split it.
- **"repeats active fact" or "repeats open task"**: that item is already recorded under the ID shown. Remove it from the bundle, or change the existing record through `lifecycle`.
- **"belongs to no inventory item"**: the bundle has an inventory, so every entry must be listed under the piece of work that produced it.
- **"keep the task open"**: a task can be completed only on work marked `verified`.
- **No write operations and `state_freshness` is `behind_upstream_ref` or `diverged_from_upstream_ref`**: the workspace Git history is missing commits its upstream ref has. Bring the workspace up to date yourself, then start again.

## Startup says the context exceeds the byte budget

The message lists the standing files and their sizes. Standing files are the
top-level files in `INDEX.json` other than `BRAIN.json`, `INDEX.json`, `MEMORY.md`,
`TODO.md` and `LESSONS.md`, and they are always delivered whole. Shorten one, move
reference material into a project folder, or raise `startup_budget_bytes` in
`INDEX.json`. Growth of `MEMORY.md`, `TODO.md` or `LESSONS.md` does not cause this.

## `WRAP UP FAILED`

A failed wrap-up preserves `state/pending_wrap_up.json` and reports the remaining replay-safe step.

Do not delete the pending file just to make the warning disappear. Correct the reported problem, then replay:

```text
PYTHON aham.py wrap-up --workspace <your-private-workspace> --recover-pending --session-id SESSION_ID
```

Already-routed entries use stable markers, so replaying the same transaction does not duplicate them.

## The previous session crashed

Look for the latest durable checkpoint:

```text
PYTHON aham.py resume --workspace <your-private-workspace>
```

If the checkpoint recorded project Git state:

```text
PYTHON aham.py resume \
  --workspace <your-private-workspace> \
  --repo <project-folder>
```

Resume only after the command verifies that the checkpoint belongs to this Brain and that recorded repository state is still compatible.

## MemPalace is missing or unavailable

MemPalace is optional. The local Brain files remain the durable source of truth.

Check the configured state with:

```text
PYTHON aham.py memory status --workspace <your-private-workspace>
```

If MemPalace is unavailable, continue without semantic recall. Do not rebuild or delete the Brain because an optional memory service is offline.

If you want to restore MemPalace, use the original MemPalace project's installation and initialization instructions, then reconnect it through `scripts/semantic_memory.py configure`.

## An external skill says `REVIEW` or `FAIL`

The source was intentionally left in quarantine and was not activated.

Do not move it into `external/` manually. A `PASS` scan is required before activation, and an existing working copy should remain untouched when a replacement fails review.

You can inspect reviewed sources with:

```text
python3 scripts/external_sources.py list
```

## Git history says no identity is configured

Git needs a name and email to create a local commit. Aham Brahmasmi does not invent them.

Either configure Git yourself or initialize the optional Brain history with values you choose:

```text
python3 scripts/git_transport.py init \
  --workspace <your-private-workspace> \
  --author-name "Your chosen name" \
  --author-email "your-address@example.com"
```

This still creates local history only. It does not create a GitHub account, add a remote, or upload the private Brain.

## Git snapshot refuses because unrelated files are staged

Aham Brahmasmi refuses to include unrelated staged files in a Brain snapshot.

Review what is staged in the private workspace and unstage anything that does not belong to the durable Brain snapshot. Do not force the snapshot to include third-party source trees or temporary quarantine data.

## Runtime bridge refuses an existing file

The bridge installer will not overwrite an unmanaged `.aham/runtime.md`, write through symlinks, or repair malformed managed markers by guessing.

Use:

```text
python3 scripts/runtime_bridge.py status --project <project-folder>
```

If the existing `.aham/runtime.md` belongs to something else, keep it and choose how to reconcile that conflict manually. Do not delete unrelated project instructions automatically.

## My local or future model does not load the bridge automatically

There is no universal instruction filename for every local or future runtime.

Tell it:

```text
Read and follow .aham/runtime.md before substantial work in this repository.
```

The model-neutral lifecycle still works as long as the runtime can read the file and perform the commands it claims to support.

## I do not have Git

Git is optional for the private Brain. You can still use the local durable files, checkpoints and wrap-up lifecycle.

Features that specifically require Git, such as Git-backed history or repository-state verification, should be reported as unavailable rather than silently faked.

## I do not know Python

You do not need to learn Python to use the normal guided setup. The assistant is expected to run the included commands when Python 3 and local command execution are available.

If a supported Python interpreter is unavailable, stop the automated setup and
follow `docs/BEFORE_YOU_START.md` with your assistant. Do not claim setup worked
until the actual workspace check succeeds.

## I do not know which folder is the Brain

The public Aham Brahmasmi repository is the framework. Your private Brain workspace is a separate folder containing files such as:

```text
BRAIN.json
MEMORY.md
TODO.md
LESSONS.md
projects/
history/
state/
```

Do not put personal memory into the public framework repository.

## Still uncertain

Do not guess around a safety warning. Keep the files as they are, run `scripts/doctor.py`, and use the exact error message to decide the next step. Optional components can remain disabled while the durable Brain stays intact.

## The writer says runtime trust is absent

The assistant name does not grant writes. The owner chooses trust with
`aham.py trust-runtime NAME --workspace WORKSPACE --confirm NAME`, then the
assistant starts with verified capabilities and uses the returned session ID.
See `docs/ASSISTANT_ACCESS.md`; never run owner controls without authorization.

If legacy pending work prevents a trust change and no runtime can recover it,
the owner can run `aham.py recover-access --workspace WORKSPACE --confirm WORKSPACE_ID`
using the exact workspace_id in BRAIN.json. This returns a held session limited
to recovery operations. Pass that `--session-id` to the reported recovery command.
It does not grant new work or create trust. Recover first, then record the owner's
trust choice and start normally. Confirmation records intent, not human authentication.

## Workspace permissions or location need attention

On POSIX, the containing Brain directory should have owner-only mode 0700. Doctor
checks it without changing it. The owner can run `chmod 700` on that chosen directory
and check again. Do not change unrelated parents or delete a workspace to repair a
mode. Setup creates private files/directories; this is not encryption.

On native Windows, the selected workspace and bridge folder need a protected access
list owned by the current user, admitting only that user, SYSTEM and Administrators.
Doctor diagnoses drift without rewriting access. Ask the owner to review that
folder’s Security settings, or choose a new absent destination for setup/restore.
Do not broaden access or modify unrelated parent folders to silence the check.

A sync-root warning is a path hint. Check your sync app's settings and choose a
local active folder; custom roots may be missed. See `docs/BEFORE_YOU_START.md`.

## Committed state is corrupt

Keep the failing command/output and preserve the workspace. Restore a verified
portable backup into a separate empty folder using `aham.py restore --input BUNDLE
--workspace DESTINATION`. Do not hand-edit operation records or delete pending
metadata to manufacture readiness. Run `aham.py check` on the restored workspace.

## Credential hygiene warning

The check found possible secret material in selected managed configuration, or
could not safely inspect a file. It reports the location without printing values.
Review it privately. Follow [credential hygiene](CREDENTIAL_HYGIENE.md): switch
**every** consumer to runtime platform-login lookup, test **each** one, then revoke
the exposed key. The check never changes configuration or revokes credentials.
