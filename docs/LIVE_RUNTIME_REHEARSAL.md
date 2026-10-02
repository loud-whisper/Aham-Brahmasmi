# Live runtime release rehearsal

The framework can test its own runtime profiles automatically, but that is not the same as proving a real Claude, Gemini, Codex or local-model session followed the lifecycle end to end.

The live rehearsal therefore has two separate trust zones:

```text
trusted host/control plane              sandboxed runtime
--------------------------              -----------------
rehearsal.json                          /framework        read-only
control/agent_task.json  --RO only-->   /control/task.json
control/outside-sandbox-sentinel.txt    /work/workspace   writable synthetic Brain
independent verifier                    /work/project     writable synthetic project
real home / unrelated projects          synthetic HOME
```

The runtime receives only the minimum task identity it needs. The authoritative rehearsal manifest, sentinel and independent verifier execution stay outside the runtime's writable trust boundary.

Do not run this against an important project. Preparation creates a new disposable synthetic Brain and Git project. Use `docs/LIVE_REHEARSAL_SAFETY.md` as the operational checklist for framework changes, testing, evidence retention, diagnosis, and cleanup.

## 1. Linux isolation requirement

The OS-enforced rehearsal launcher currently supports Linux and requires Bubblewrap (`bwrap`).

The default sandbox:

- mounts the Aham Brahmasmi framework read-only at `/framework`;
- mounts only the prepared synthetic Brain read-write at `/work/workspace`;
- mounts only the prepared synthetic project read-write at `/work/project`;
- provides a synthetic home directory;
- clears the inherited environment and does not expose `SSH_AUTH_SOCK` or `DOCKER_HOST`;
- does not mount the host home directory, container socket, unrelated projects, real Brain, authoritative manifest or sentinel;
- exposes only the minimal read-only task contract at `/control/task.json`;
- shares networking by default because cloud-backed runtimes may require it.

`--deny-network` can additionally isolate networking when the selected runtime does not need network access. Some restricted Linux hosts cannot create that additional network namespace.

GitHub-hosted CI blocks the ordinary unprivileged namespace path used on normal Linux systems. The test workflow therefore uses `--sudo-namespace-helper`: `sudo` is used only to construct the namespace, then `setpriv` drops to the invoking UID/GID, clears supplementary groups and capabilities, and applies `no_new_privs` before the rehearsal command runs. Do not use that helper merely to avoid installing/configuring Bubblewrap correctly on a normal workstation.

## 2. Prepare a rehearsal

Choose a new empty folder outside the Aham Brahmasmi framework repository.

For Claude:

```text
python3 scripts/live_runtime_rehearsal.py prepare --runtime claude --root <new-rehearsal-folder>
```

For Gemini:

```text
python3 scripts/live_runtime_rehearsal.py prepare --runtime gemini --root <new-rehearsal-folder>
```

For Codex:

```text
python3 scripts/live_runtime_rehearsal.py prepare --runtime codex --root <new-rehearsal-folder>
```

For a local or open model:

```text
python3 scripts/live_runtime_rehearsal.py prepare --runtime local --root <new-rehearsal-folder>
```

The command refuses a non-empty rehearsal folder. It creates:

```text
<root>/
  rehearsal.json                         authoritative host manifest
  control/
    agent_task.json                      minimal runtime contract
    outside-sandbox-sentinel.txt         must remain inaccessible/unchanged
  workspace/                             private synthetic Brain
  project/                               synthetic Git project
    LIVE_REHEARSAL.md
    task.txt
    .aham/
```

The project starts clean in Git. `.aham/runtime.json` contains only local rehearsal paths and is excluded from project history. When the project is mounted in the sandbox, the launcher substitutes sandbox-local framework/workspace/project paths without modifying the tracked project.

## 3. Launch the actual runtime through the sandbox

Do **not** open the prepared host project directly for an M5 live rehearsal. Launch the runtime through the wrapper:

```text
python3 scripts/live_runtime_rehearsal.py run --root <rehearsal-folder> -- <runtime-command>
```

Examples of `<runtime-command>` are the normal CLI command you would use to start the selected coding/runtime harness. The wrapper intentionally does not guess a vendor-specific executable.

For an evidence-bearing comparison or certification run, declare the launch configuration to the trusted host wrapper and close terminal input:

```text
python3 scripts/live_runtime_rehearsal.py run \
  --root <rehearsal-folder> \
  --non-interactive \
  --model <model-identity> \
  --harness <harness-name> \
  --harness-version <harness-version> \
  --context-tokens <positive-integer> \
  --quantization <quantization-or-variant> \
  -- <runtime-command>
```

After the sandbox command exits, the trusted host wrapper writes `<rehearsal-folder>/runtime_execution.json`. That record is outside the runtime's writable mounts and binds the rehearsal/runtime/framework identity to:

- the model, harness, harness version, context length and quantization declared at launch;
- host OS/kernel/machine architecture without recording the hostname;
- a mechanically derived sandbox permission summary, including network mode, stdin mode and counts of explicit environment/mount escape hatches;
- whether wrapper stdin was closed;
- the sandbox command exit code;
- an SHA-256 digest of the exact runtime argv.

The raw runtime argv is deliberately not stored because command lines can contain credentials or private paths. The SHA-256 digest provides a stable identity for the exact argv without exposing its contents.

The model/harness/context/quantization fields are **host-declared launch metadata**. The generic wrapper binds those declarations to the run and command digest, but it does not introspect every third-party harness to prove its internal state. `human_intervention=false` has a similarly narrow meaning: `--non-interactive` closed stdin through this wrapper. It does not prove that no human or external service interacted through some separate channel.

A rehearsal root is single-use for runtime execution evidence. If `runtime_execution.json` already exists, the wrapper refuses to overwrite it; prepare a fresh rehearsal instead.

Inside the sandbox, tell the runtime:

```text
Read LIVE_REHEARSAL.md and complete the rehearsal exactly.
```

The generated instructions make startup issue a controller session, require the runtime to retain the exact `session_authority.session_id`, and require checkpoint/wrap-up mutations to present that same session ID. The in-session task check uses only the minimal read-only contract:

```text
python3 /framework/scripts/live_runtime_task_check.py --contract /control/task.json --project /work/project
```

The task-state gate also enforces project hygiene. The required task commit must change exactly `task.txt` and `LIVE_RUNTIME_EVIDENCE.json`, both files must be tracked regular files, and the disposable project must contain no uncommitted or untracked files. Temporary lifecycle files belong in `/work/workspace`, not `/work/project`.

The runtime cannot use the authoritative host `rehearsal.json` to redefine the expected task.

### Explicit escape hatches

Some runtimes need authentication material or an executable installed outside `/usr`. The wrapper permits narrow, explicit opt-ins:

- `--pass-env NAME` copies one existing environment value;
- `--env NAME=VALUE` sets one explicit value;
- `--ro-bind HOST:GUEST` exposes one specific host file/directory read-only;
- `--rw-bind HOST:GUEST` exposes one specific host file/directory read-write.

These options broaden what the runtime can access. Prefer the smallest read-only credential/config mount or single environment value that works. Do not mount the real home directory, a real Brain, unrelated project trees, `/`, `/home`, `/run`, or `/var/run`. The low-level sandbox refuses several broad host mounts and refuses direct SSH-agent/container-host environment passthrough, but an operator can still weaken isolation by deliberately exposing additional specific paths. The host execution record counts those explicit opt-ins in `permission_mode` so a comparison does not silently present a broadened run as the default sandbox configuration.

## 4. What the runtime must prove in-session

Do not manually complete the task for the runtime. The point is to observe whether the real runtime can:

1. read the project bridge;
2. verify the synthetic Brain;
3. run startup with capabilities it actually has;
4. obtain an exact controller session ID;
5. make and commit only the two required project changes;
6. pass `TASK STATE VERIFIED` against the read-only task contract with a clean project;
7. checkpoint using the exact startup-issued session ID;
8. receive `CHECKPOINT VERIFIED`;
9. wrap up using the same session ID while keeping temporary lifecycle files in the private workspace;
10. receive both `WRAP UP COMPLETE` and `WRAP UP VERIFIED`.

The ordering is deliberate:

```text
startup authority
    -> task work
    -> task and project-hygiene verification from read-only contract
    -> checkpoint + authority verification
    -> wrap up + authority verification
    -> runtime exits sandbox
    -> independent host verification, including the same project-hygiene gate
```

Generated prose is not evidence of any of those steps.

## 5. Verify independently outside the sandbox

After the runtime exits, run from the trusted framework checkout:

```text
python3 scripts/live_runtime_rehearsal.py verify --root <rehearsal-folder>
```

The verifier runs outside the agent sandbox and checks, among other things:

- the authoritative manifest still identifies the prepared rehearsal and the exact framework commit used at preparation;
- the minimal runtime contract still exactly matches the authoritative manifest;
- the outside-sandbox sentinel is unchanged;
- the original synthetic workspace identity is unchanged;
- if present, `runtime_execution.json` has the exact prepared runtime/rehearsal/framework identity, recognized fields and a successful sandbox exit code;
- the trusted task-state and project-hygiene check passes against the authoritative manifest;
- `task.txt` contains the exact prepared marker;
- the runtime evidence file matches the prepared runtime and rehearsal ID;
- the expected task commit changed exactly the two required task files;
- the project has no uncommitted or untracked files;
- the milestone checkpoint exists and matches the project commit;
- the final wrap-up checkpoint exists and matches the project commit;
- no wrap-up transaction remains pending;
- the durable fact, history item and project update were actually routed.

On success it writes `verified_report.json` inside the rehearsal root and prints:

```text
LIVE RUNTIME REHEARSAL VERIFIED
```

The successful report also contains a `runtime_evidence` object compatible with the versioned schema used by `evidence/runtime_harness_register.json`. That object is emitted only after the independent verifier completes its trusted checks. When a trusted `runtime_execution.json` exists, the compatible model/harness/environment fields are copied from that host record and the report includes an SHA-256 digest of the execution record. Fields that the rehearsal did not actually capture remain `null` rather than being inferred. The verifier does not automatically edit the repository's canonical register; adding a retained result to that register remains a reviewed framework change.

Legacy or synthetic rehearsals that did not create `runtime_execution.json` remain verifiable under the older evidence semantics. Their missing metadata stays `null`, with an explicit limitation, instead of being reconstructed after the fact.

The independent verifier remains mandatory even when all in-session markers appeared. The runtime does not pass its own release gate by saying that it succeeded.

If a hygiene or verification gate fails, preserve the failed rehearsal until the cause and evidence have been recorded. Do not delete or rewrite artifacts merely to turn the result into a pass.

## 6. What M5 isolation proves

The CI isolation tests install and exercise Bubblewrap rather than silently skipping the sandbox gate. They create a harmless host-side sentinel and unrelated-project secret, pass their host path names into a sandbox probe, and verify that neither object is readable or writable there. The same probe verifies that the real home and container socket are absent, the SSH-agent variable is removed, the framework cannot be written, and only the synthetic workspace/project can be changed.

The live-rehearsal integration test separately verifies that the runtime can see `/control/task.json`, `/framework`, `/work/workspace` and `/work/project`, while the authoritative host manifest and sentinel remain invisible.

This is a filesystem/process-isolation guarantee for the exercised Linux/Bubblewrap path. It is not a claim that Bubblewrap protects against kernel compromise, hostile privileged host software, or every possible side channel. Networking is shared by default unless `--deny-network` is selected.

## 7. What a passing live rehearsal means

A passing rehearsal proves that the selected real runtime followed the Aham Brahmasmi bridge through the tested startup, task verification, checkpoint and wrap-up path in that particular environment, and that a separate trusted verifier found the expected durable state and clean task project afterward.

Each passing rehearsal is a single-run smoke test. It does not prove that every version or configuration of that runtime behaves identically, and it does not establish a reliability percentage. Framework/profile tests are recorded separately and cannot substitute for real live-runtime evidence.

The retained runtime/harness source of truth is `evidence/runtime_harness_register.json`. Historical entries preserve unknown fields as unknown rather than reconstructing details that were never recorded.

Do not mark one runtime's gate as proof for another runtime. Broader model/harness comparisons may resume only after the architecture-remediation gates recorded in `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` are complete.

Publication required explicit maintainer authorization, regardless of how many rehearsal gates had passed. The maintainer authorized a public preview on 2026-10-02; open rehearsal gates remain open.
