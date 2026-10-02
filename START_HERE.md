# Start here

You do not need to know Git, Python, command lines, or how this project is built to use the normal setup.

For the normal setup, do only this:

1. Open this project folder with the model or coding assistant you already use.
2. Tell it:

> Read `START_HERE.md` and set this up for me.

3. Answer the few questions it asks, such as where you want your private Brain stored.

The assistant should do the technical work for you and explain any choice before asking you to make it.

## Words you may see

- **Brain**: your private collection of memory, tasks, lessons, projects and recovery points.
- **framework**: this reusable Aham Brahmasmi project. It contains the machinery, not your personal information.
- **private workspace**: the separate folder that holds your own Brain.
- **runtime**: the model or tool you are using right now, such as Claude, Gemini, Codex or a local model.
- **checkpoint**: a saved recovery point so interrupted work can continue later.
- **wrap up**: the end-of-session step that sorts useful information into the right places and saves a final recovery point.
- **semantic memory**: optional search-based recall that can help find related past information. The Brain still works without it.
- **Git**: an optional version-history tool. You do not need to understand or use it for the basic Brain.
- **skill**: an optional set of instructions or tools for doing a particular kind of work.

Everything below this point is primarily instructions for the assistant performing setup.

## Instructions for the assistant

Treat the person as the owner of the Brain. Your job is to configure a new private workspace for them, not to copy an existing workspace from somewhere else.

### 0. Check the system before setup

Identify the operating system and an available Python interpreter, then run its
`--version` command. Stop unless the system and Python version are supported in
`docs/BEFORE_YOU_START.md` (Linux/macOS with Python 3.10–3.14; native Windows verified with Python 3.14). Verify
actual command execution and file tools; never simulate a check or infer tools from
the assistant name. On Windows, confirm an installed Python runtime first; a
launcher can install a missing runtime, which requires the owner’s approval. WSL
has no separate verification claim. Run `PYTHON aham.py check` for prerequisites and a local folder suggestion;
without `--workspace`, it deliberately does not report a ready Brain.

Use the hand-offs in `docs/BEFORE_YOU_START.md` for permission windows, restarting
the terminal after installing Python, and approval before administrator commands.
If a check fails, keep the exact command/output and use troubleshooting. Do not
repair framework code during setup. Chat-only users follow `docs/ASSISTANT_ACCESS.md`.

### 1. Verify capabilities and select the private workspace

Verify that this session can read and write files and run local Python commands.
Do not infer tools from the assistant name. Follow `docs/PLATFORM_SUPPORT.md` for
the supported platform boundary. If command tools are absent, use the user-run
chat paste workflow in `docs/ASSISTANT_ACCESS.md`; do not simulate local setup.

Explain that this framework folder contains reusable machinery. Memory, tasks,
lessons and personal paths belong in a separate private workspace selected by the
owner. Never copy another existing Brain. Ask for the destination and explain
where information will accumulate. Use the local suggestion from `aham.py check`
if they want one, after checking it is outside sync. Do not require Git, MemPalace or skills.

### 2. Create and check

In commands below, `PYTHON` means the Python 3 interpreter actually available in
this session. Replace placeholders with the user's choices and quote paths as
needed for their terminal. Run from the framework folder:

```text
PYTHON aham.py setup --workspace WORKSPACE
PYTHON aham.py check --workspace WORKSPACE
```

Setup refuses a workspace inside this public framework or an existing non-empty
destination. Stop on failure, report the exact command and output, and use
`docs/TROUBLESHOOTING.md`. Do not modify the framework to make setup pass.

### 3. Ask the owner about writes and start

Explain that the owner can let their chosen assistant save durable state or keep
it read-only. Never invoke owner trust controls without explicit authorization.
If the owner authorizes writes, record their chosen runtime name:

```text
PYTHON aham.py trust-runtime RUNTIME --workspace WORKSPACE --confirm RUNTIME
```

Use the same normalized name for confirmation. Listed and unlisted tools follow
the same trust rule. Start with only capabilities actually verified:

```text
PYTHON aham.py start --workspace WORKSPACE --runtime RUNTIME --mode regular --compact
```

Append `--capability read_files`, `--capability write_files`, and
`--capability run_commands` only when each is available. Writes require recorded
owner trust, reported write capability and a successful controller writer probe.
The probe verifies local controller writes, not the assistant's own tool access.
Record the returned session ID; use it for every save or wrap-up. No runtime name
alone grants write authority. Degraded mode is read-only. Quick mode requires
already-loaded verified context and `--context-loaded`.

Recover pending work before starting a new task. Use `start --json` for full
diagnostics and `aham.py resume` to verify a checkpoint. See
`docs/ASSISTANT_ACCESS.md` for existing-workspace migration and trust revocation.

### 4. Offer optional connections

After core setup succeeds, explain optional components separately:

- Git history: `docs/GIT_TRANSPORT.md`. Do not configure a remote or push private
  state without a separate request; ask for author identity only when needed.
- Recall: `aham.py memory setup --workspace WORKSPACE` shows available choices.
  Offline keyword recall requires no installation; MemPalace stays optional and
  user-installed. See `docs/MEMORY_CONNECTION.md` for project scope and indexing.
- Skills: `aham.py skills --help` and `docs/SKILL_SCANNER.md`. Sources remain in
  quarantine until required review passes. Never waive FAIL or incomplete scans.
  Superpowers still has unaccepted REVIEW findings; it is not a ready default.
- Project bridge: ask which project folder to connect, then run:

```text
PYTHON aham.py connect --runtime RUNTIME --workspace WORKSPACE --project PROJECT
```

Known profiles use their verified instruction mechanism while preserving other
instructions. Unlisted runtimes use manual reading of `.aham/runtime.md`. Private
local paths are kept in ignored `.aham/runtime.json`. A bridge grants no tools,
hooks or permissions. Read the full listed `SKILL.md` before using a skill.

### 5. Save and report evidence

Read `docs/LIFECYCLE.md`. After a meaningful milestone passes relevant checks,
use `aham.py save`; when the user says wrap up, use `aham.py wrap-up`. Pass the
workspace and current session ID. Commands retain their existing options; run
`--help` for details. Require actual `CHECKPOINT VERIFIED` or `WRAP UP VERIFIED`
output before claiming completion. Preserve pending recovery after failure.
Never record intended work as completed work.

Finish with a short report: chosen workspace, verification result, runtime,
verified capabilities, writer authority and probe result, optional connections,
project bridge, pending recovery and next step. Report only observed facts.

## If something goes wrong

If Python command execution is available, the assistant should run:

```text
PYTHON aham.py check --workspace WORKSPACE
```

Add `--project PROJECT_PATH_CHOSEN_BY_USER` when a connected project is also involved. Explain the result in ordinary language. Do not guess around a safety warning.

The plain-language recovery guide is `docs/TROUBLESHOOTING.md`.

## If the person wants to inspect everything themselves

Use `docs/MANUAL_SETUP.md` instead of the assisted path.
