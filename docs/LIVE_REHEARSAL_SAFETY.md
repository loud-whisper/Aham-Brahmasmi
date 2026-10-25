# Live rehearsal safety checklist

Use this checklist whenever a real runtime or harness is tested. Framework development, disposable runtime execution, evidence collection, diagnosis, and cleanup are separate activities.

## Before changing framework code

- Work on a feature or fix branch, never directly on `main`.
- Read `PROJECT_CHECKLIST.md`, `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md`, and the relevant test-plan section before editing.
- Keep framework changes generic. Do not add personal paths, hostnames, credentials, private launcher names, or machine-specific configuration.
- Identify the exact failure being fixed before changing code. Do not weaken a verifier merely to make a failed rehearsal pass.

## Before a live rehearsal

- Use a fresh disposable rehearsal root outside the framework repository.
- Run the runtime through `scripts/live_runtime_rehearsal.py run`, so the Bubblewrap isolation path is used rather than opening the host rehearsal project directly.
- Keep the real home directory, real Brain, unrelated projects, SSH agent, and container socket outside the sandbox unless a narrow explicit exception is genuinely required.
- Record the framework commit, runtime profile, rehearsal ID, and any explicit sandbox escape hatches needed for the run.
- Confirm the prepared project is clean before starting the runtime.

## During the rehearsal

- Treat the generated `LIVE_REHEARSAL.md` and read-only `/control/task.json` contract as the task authority visible to the runtime.
- The only required task commit changes are `task.txt` and `LIVE_RUNTIME_EVIDENCE.json`.
- Keep temporary lifecycle files, including the wrap-up bundle, in the synthetic private workspace, not in the disposable project.
- Do not copy the host rehearsal manifest into the project, create Git backups, or add unrelated runtime configuration to the project.
- Require actual machine proof markers. Runtime prose alone is not evidence of success.
- Stop at a failed gate. Do not continue checkpoint or wrap-up work after a required verification command fails.

## Classifying the result

- Count a runtime as passing only when the trusted host verifier prints `LIVE RUNTIME REHEARSAL VERIFIED`.
- A single pass is a smoke test in one tested environment, not a reliability percentage.
- Preserve a failed project and workspace unchanged until the cause is understood and the evidence needed for diagnosis has been recorded.
- Keep framework defects and runtime-behavior defects distinct when recording the cause.
- Retained runtime/harness results belong in `evidence/runtime_harness_register.json`; do not invent metadata that was not captured.

## Before merging framework changes

- Add or update regression tests for the observed failure.
- Require Foundation verification and the complete unit suite to pass on the branch.
- Run a fresh live rehearsal for the affected runtime when the change alters live-runtime behavior.
- Recheck unrelated runtime paths when the change can affect shared lifecycle behavior.
- Merge only after the code change and retained test evidence agree.

## Cleanup

- Clean disposable rehearsal and framework directories only after the result and evidence have been recorded and no further diagnosis depends on them.
- Cleanup is housekeeping. It must never be used to convert a failed result into a passing result.
