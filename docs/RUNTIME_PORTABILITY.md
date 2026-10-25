# Runtime portability

Aham Brahmasmi is designed so the durable Brain belongs to the user rather than to one model or command-line tool.

## The important distinction

A runtime name is not a permission grant.

Selecting `claude`, `gemini`, `codex`, `local`, or another runtime does not automatically mean that runtime can read files, write files, run shell commands, use Git, access the network, load skills, or connect to semantic memory.

The runtime must verify its actual capabilities in the active session. The startup executable records only those reported capabilities.

## Startup executable

When Python command execution is available, use:

```text
python3 scripts/startup.py --workspace PATH --runtime RUNTIME --mode regular
```

Add only capabilities that have actually been verified:

```text
--capability read_files
--capability write_files
--capability run_commands
--capability git
--capability network
--capability skill_loader
--capability semantic_memory
```

For machine-readable output, add:

```text
--json
```

The report verifies the private workspace, identifies the runtime profile, shows the selected mode, reports only explicitly verified runtime capabilities, inspects recovery state, summarizes the newest durable checkpoint, reports semantic-memory status without requiring it, and shows whether runtime writes are actually established.

## Quick mode

Quick mode is only valid when current context is already loaded and verified. The executable therefore requires:

```text
--mode quick --context-loaded
```

Without that confirmation, startup is blocked rather than pretending the context is current.

## Unknown runtimes

An unrecognized runtime name is not an error. It falls back to `runtime_profiles/unknown.json`.

The requested runtime name is preserved in the report, but no capabilities are inferred from it. This allows a future or uncommon runtime to use the neutral core safely.

## Workspace write trust

Both listed and unlisted names require the workspace owner's explicit trust,
reported `write_files`, and a successful transient controller writer probe before
startup issues write authority. Degraded mode stays read-only. Trust is recorded
through the writer ledger and can be revoked; profiles only select instructions.
The probe verifies the controller backend, not model tools or instruction compliance.

Use `aham.py start --compact` for compact metadata and `aham.py trust-runtime` for
the owner's confirmed choice. See `docs/ASSISTANT_ACCESS.md` for trust, revocation,
existing-workspace migration and chat paste mode. Never invoke owner controls
without the owner's authorization. Existing scripts remain compatible.

## Switching runtimes

The runtime profile is not stored as the owner of durable state. Checkpoints, memory, tasks, lessons, project state and history remain in the same private workspace.

A different runtime can open the same workspace, run Regular startup, and see the same verified durable checkpoint and recovery state. No model-specific handoff file is required by the core.

## Skills and semantic memory remain optional

A native skill loader is never required for basic startup. Reviewed external sources can still live in the private workspace even when a runtime has no native skill mechanism.

Semantic memory is also optional. If it is not configured, startup reports `not_configured`. If it is configured but the runtime has not verified semantic-memory access, startup reports `configured_not_verified` and continues with the local durable workspace.

## What runtime evidence means

Automated framework/profile tests verify the model-neutral bridge and lifecycle mechanics. They do not prove that an authenticated external runtime followed the lifecycle in a real session.

A named live-runtime gate is supported only by an independently verified live rehearsal for that runtime. The retained source of truth is `evidence/runtime_harness_register.json`. A passing live rehearsal is one single-run smoke test in one environment, not a reliability percentage and not proof for other model, harness, version or permission configurations.

The current generated status in `docs/STATUS.md` and `PROJECT_CHECKLIST.md` is derived from that register. Unknown historical metadata remains unknown rather than being inferred.
