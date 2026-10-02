# R7: newcomer flow and diagnostic tests

The controlling four human walkthrough gates remain unchecked until real
nontechnical testers complete setup, switching and interrupted-operation recovery.
Automated tests verify the controllers and documentation before that hand-off.
User decisions: D9 enforces owner-only POSIX setup permissions; D3 authorizes
native Windows implementation at W1. Current Windows mutation stays unsupported.

## Before implementation

- Reproduce setup's process-default permissions under a permissive umask; require
  0700 directories and 0600 files within a newly created private workspace. Do not
  change unrelated parents. Refuse unsafe destination aliases before any copying.
- Reproduce doctor readiness without a selected workspace and when a checkpoint
  is pending. Require a concrete next action, running interpreter, plain verbs and
  active-session guidance. Doctor must remain read-only.
- Require explicit unsupported-platform/Python guidance and never infer assistant
  command tools from a profile. Step 0 checks OS, Python 3.10–3.14 and real command
  availability before setup. Never repair the framework to force setup success.
- Check private workspace access modes and expose a permission repair action;
  optional external source read-only mode is not a private-workspace access grant.
- Warn on verified common sync roots, with canonical containment and documented
  false positives/custom-folder limitations; suggest a local folder outside the
  Desktop/Documents/cloud roots. Do not claim universal sync detection.
- Detect corrupt canonical state and invalid requested project bridges without
  claiming readiness or exposing a traceback. Distinguish core data readiness from
  startup-issued runtime write authority.
- Move internal TODO/review/checkpoint notes to `docs/dev/`, update links and
  test references. Move generated status/evidence out of newcomer README into
  `docs/STATUS.md`; keep canonical register reconciliation and historical scope.
- Preserve the maintainer's personal story, add three-step setup, official origin,
  supported platforms and explicit chat-only route. Verify all published command
  examples from local help or official sources; do not invent installer steps.

## Regressions and review

Use synthetic workspaces only. Snapshot directory entries, file bytes and modes
around read-only diagnosis and failed setup cases. Preserve A1 trust/probe/chat,
M5 authority/recovery and R5 containment regressions. Exercise actual filesystem
permissions on POSIX and simulated sync-root containment separately. Windows ACL
semantics and native lifecycle evidence belong to W1.

Design the walkthrough protocol and blank evidence template for two or three
testers with no Git/Python knowledge. Record synthetic outcomes and stuck points,
never private Brain content. A scripted controller rehearsal does not count as
a human walkthrough. No tester result is prefilled as PASS.

Save red tests remotely with CI skipped; run targeted tests, Foundation, link/path
reconciliation and full suite locally. Run one final ready framework matrix after
the local tests pass. Save/PR/merge the implementation checkpoint even when human
outcomes remain pending, preserving the unchecked acceptance gates and hand-off.

## Expanded local findings before correction

The corrected initial umask test reproduced 0700/0600 violations; its first
invocation had a missing script-import path and is retained as a harness failure.
Expanded snapshots then caught ledger reads creating a directory during diagnosis.
Recovery review reproduced a legacy pending/no-trust deadlock, then constrained
the owner access path to exact held-session recovery. Further failing tests covered
cached state ahead of a missing ledger, false readiness for an invalid requested
bridge, permission-error tracebacks, and a configuration-selected instruction path
outside the project. Final review reproduced two misleading diagnoses: Windows
access reported as verified without an ACL check and stale-session recovery
guidance. Eighteen targeted regressions pass after these corrections. Foundation,
documentation reconciliation and the full local 390-test suite passed with one
expected skip. Exact acceptance head
`94f88d1053c9479606b25ec9ed2ca2cc9997ab27` passed all six jobs in workflow
`36915089427` (390 Linux tests, 355 portable tests per job, two skips per macOS
job, Windows unsupported-write refusal). PR #61 merged as
`758be6478b2fc5a06bf30a898b9eaa300e9791a2`. One matrix used 599 summed runner
seconds or 13 minutes rounding each job up; this is not billing usage. No hosted
red/draft gate or extra dispatch was used. Human outcomes remain pending.
