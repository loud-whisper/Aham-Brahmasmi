# Changelog

## Unreleased

- Startup reads a bounded packet replayed from the operation ledger (`aham.py context --startup`). The
  append-only `MEMORY.md`, `TODO.md` and `LESSONS.md` projections no longer count toward
  `startup_budget_bytes`, so completed tasks and replaced facts leave startup.
- **Changed:** Quick mode is now a light cold start and is read-only. `start --mode quick` no longer
  needs `--context-loaded` (the flag is accepted and ignored) and its session allows no save or
  wrap-up; run `start --mode regular` first. `core/startup.json` is version 3 and
  `core/brain.json` sets `modes.quick.allow_validated_writes` to false.

## 0.1.0-preview.1

Launch edition, 2026-10-25.

- Private, user-owned workspaces with checked writers, receipts and recovery checkpoints.
- Model-independent runtime bridges, explicit trust and a bounded chat paste workflow.
- Optional Git history, portable backup, scoped memory and reviewed external skills.
- Credential lookup through a user-installed GitHub CLI and redacted diagnostics.
- Workspace drift checks and platform-specific containment safeguards.

This preview has open newcomer and live-runtime validation gates. See `docs/STATUS.md` and `PROJECT_CHECKLIST.md` before relying on a particular runtime or platform.
