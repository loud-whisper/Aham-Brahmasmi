# Changelog

## Unreleased

- Startup reads a bounded packet replayed from the operation ledger (`aham.py context --startup`). The
  append-only `MEMORY.md`, `TODO.md` and `LESSONS.md` projections no longer count toward
  `startup_budget_bytes`, so completed tasks and replaced facts leave startup.
- **Changed:** Quick mode is now a light cold start and is read-only. `start --mode quick` no longer
  needs `--context-loaded` (the flag is accepted and ignored) and its session allows no save or
  wrap-up; run `start --mode regular` first. `core/startup.json` is version 3 and
  `core/brain.json` sets `modes.quick.allow_validated_writes` to false.
- **Changed:** a session issued by `start` may save or wrap up only after `aham.py confirm-context`
  reports `CONTEXT CONFIRMED`. Read the packet with `context --startup --part N` and present each
  `part_sha256`. Recovery commands and owner controls are unaffected. `start --mode regular
  --upgrade-from SESSION_ID` keeps the parts a Quick session already confirmed.
- **Changed:** the chat wrap-up response is version 2 and must echo `context_packet_sha256` and
  `context_limit_bytes` from the exported template. A version 1 response is refused; export fresh
  context and ask again.
- Wrap-up bundles may carry an `inventory`: every piece of work in the session with an evidence
  label, its evidence, a next action and the entries it routed. With an inventory, completed work
  in the checkpoint is taken from the items marked `verified`. Bundles without one work as before.
- **Changed:** a new wrap-up refuses an entry over its size cap (`wrap_up.item_caps_bytes` in
  `core/lifecycle.json`) and an entry that repeats an active fact or open task of the same projects,
  naming the existing ID. Pending and committed transactions replay without these checks.
- A wrap-up bundle with an inventory may carry `lifecycle` changes: `task_complete`, `task_cancel`,
  `fact_supersede` and `fact_retract`, each naming the inventory item that justifies it. A task is
  completed only on work marked `verified`. An interrupted wrap-up applies each change exactly once
  on recovery. `aham.py tasks` and `aham.py facts` list records and apply single changes.
- Wrap-up receipts gain a `summary`: outcome, routed counts, tasks completed and still open, record
  changes, Git snapshot status, whether the snapshot is in the local upstream ref, and the next action.
  `wrap_up.py --snapshot` takes a local Git snapshot after the wrap-up commits. Nothing is pushed.
- Startup `state_freshness` compares the workspace with its local upstream-tracking ref without
  fetching. **Changed:** a Regular start on a workspace that is behind or diverged from that ref
  allows reading but no save or wrap-up. `latest_checkpoint` reports `age_days` and `stale`
  (`checkpoint.stale_after_days` in `core/lifecycle.json`).

## 0.1.0-preview.1

Launch edition, 2026-10-25.

- Private, user-owned workspaces with checked writers, receipts and recovery checkpoints.
- Model-independent runtime bridges, explicit trust and a bounded chat paste workflow.
- Optional Git history, portable backup, scoped memory and reviewed external skills.
- Credential lookup through a user-installed GitHub CLI and redacted diagnostics.
- Workspace drift checks and platform-specific containment safeguards.

This preview has open newcomer and live-runtime validation gates. See `docs/STATUS.md` and `PROJECT_CHECKLIST.md` before relying on a particular runtime or platform.
