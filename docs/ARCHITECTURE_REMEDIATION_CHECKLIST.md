# Architecture remediation checklist

This checklist turns the 2026-09-18 Astra architecture review into the ordered implementation plan for Aham Brahmasmi.

Source review: `review/astra-architecture-2026-09-18` -> `docs/dev/reviews/2026-09-18-astra-architecture-review.md`, reviewed against framework commit `a94f2a79242ee835b90b6d68bbb2a298bd80d035`.

## Anti-drift rule

Work from the top down. Before starting implementation, identify the first unchecked milestone whose prerequisites are satisfied. Do not start later architecture work merely because it is interesting or easier.

For every milestone:

1. reproduce the relevant failure with a regression test before changing behavior;
2. make the smallest generic change that closes the demonstrated gap;
3. run foundation verification and the full unit-test suite;
4. add failure/recovery tests required by that milestone's acceptance gate;
5. update this checklist only after the acceptance gate is demonstrated;
6. work on a feature/fix branch, never directly on `main`;
7. keep the framework model-neutral and do not weaken verification to obtain a pass.

Do not resume broad runtime/harness expansion, including the DeepSeek Harness comparison, until M1-M6 are complete. Existing runtime evidence remains historical evidence, but it does not override these architecture gates.

## Must fix before broader runtime testing

### M1. Canonical operations and immutable identity

Goal: an accepted operation can never silently lose, reinterpret, or overwrite information.

- [x] Define strict versioned schemas for new requests, persisted pending transactions, completed receipts, and recovery input.
- [x] Introduce immutable `operation_id` semantics: one ID is permanently bound to one canonical payload.
- [x] Compute and persist a canonical payload digest [content fingerprint].
- [x] Exact retry of the same operation returns/reuses the same receipt without duplicating state.
- [x] Reusing an operation ID with different content fails before any mutation.
- [x] Validate persisted pending state through the same canonical validation path used for new requests.
- [x] Keep aliases only at the request boundary; persisted state uses canonical field names only.
- [x] Reject unknown fields, duplicate/conflicting fields, and malformed persisted transactions before mutation.
- [x] Verify accepted destination content, not merely the presence of marker text.
- [x] Ensure free-form user/model content cannot impersonate control metadata or persistence markers.
- [x] Define retry/status behavior so a caller that loses terminal output can safely determine whether an operation committed.

Acceptance gate:

- [x] Regression for Astra F1 passes: reused operation/session identity cannot overwrite or contradict previously accepted content.
- [x] Regression for F2 passes: marker text inside content cannot satisfy persistence verification.
- [x] Regression for F3 passes: malformed/alias-shaped persisted pending state cannot recover as a false success.
- [x] Regression for F6 passes: retry after lost output is idempotent [safe to repeat] when it is the same operation.
- [x] Unknown/conflicting input causes zero durable mutation.
- [x] A fresh reader can enumerate exactly what the accepted operation committed.

M1 acceptance evidence: branch `fix/astra-m1-canonical-operations`, regression-first commit `7dda652be7843fecf52e7e94dd0d307bd9ccd2fe` failed the unit-test gate while foundation verification remained green; implementation and legitimate-recovery fixtures then passed the full Foundation checks workflow at commit `8b685184e79088dcd0bfb8b1a0ded39cb629cb6c` (workflow run `35401525168`). Completed receipts persist canonical payloads, payload digests, and explicit committed-item descriptors, and `--status OPERATION_ID` independently verifies completed state.

### M2. Single writer, revisions, and crash-safe commit boundary

Goal: concurrent work and interruption cannot silently lose accepted state.

Prerequisite: M1 complete.

- [x] Introduce one authoritative writer path for Brain mutations.
- [x] Serialize writers for a workspace/Brain.
- [x] Add monotonic revisions [always-increasing version numbers].
- [x] Require `expected_revision` for mutations that depend on current state.
- [x] Acquire writer coordination before checking or creating pending state.
- [x] Define an explicit committed-operation boundary separate from projection/update progress.
- [x] Make crash recovery replay from committed operation records rather than infer success from partial files.
- [x] Include checkpoint and wrap-up mutations under the same coordination model.
- [x] Document filesystem durability assumptions and add directory synchronization where supported/needed.

Acceptance gate:

- [x] Regression for Astra F4 passes with independent concurrent processes: all accepted operations survive, or one receives an explicit conflict.
- [x] Kill/restart tests at each durable write boundary conserve committed state.
- [x] A partial operation is reported as pending/recoverable, never complete.
- [x] A fresh process can identify the last committed revision deterministically.

M2 acceptance evidence: branch `fix/astra-m2-writer-revisions`. Regression-first commit `7f74a2139b36578d75e592b3a6bacaaeae5445e1` preserved green foundation verification while the new unit gate failed nine times in workflow run `35401873439`, including a reproduced F4 collision between independent wrap-up processes and absent revision/crash-boundary semantics. The authoritative writer, shared lock, monotonic revision ledger, optimistic `expected_revision` checks, and immutable committed-operation boundary passed the full workflow at commit `dced0c8aa7114fdf84a81577ed82411f7e86dded` (run `35402371599`). Stronger standalone-checkpoint crash/recovery coverage also passed at commit `5f106e5bf02142c84eee52d929b25121f61517c5` (run `35402476788`). `docs/STATE_WRITER.md` defines the commit boundary, recovery semantics, POSIX lock behavior, directory synchronization, and filesystem durability assumptions; its commit `e828b8e88c8371a0b430630ba7e5916bab16995a` passed workflow run `35402537690`.

### M3. Stable project identity and deterministic recovery

Goal: recovery always selects the correct project state and never silently falls back to stale state.

Prerequisite: M2 complete.

- [x] Introduce stable project IDs separate from display names and filenames.
- [x] Store project display name/location as attributes, not identity.
- [x] Replace lossy project-name slugs as identifiers; detect migration collisions.
- [x] Maintain per-project checkpoint heads rather than one ambiguous global latest selection.
- [x] Order committed checkpoints by monotonic revision, not timestamp/filename ordering.
- [x] Reconcile latest pointers/indexes with authoritative committed records.
- [x] Report corrupt/missing newer state explicitly as degraded recovery rather than silently choosing an older checkpoint.
- [x] Strengthen repository identity beyond branch/ancestry where practical.
- [x] Define checkpoint verification scope for dirty/untracked/unsaved artifacts so `VERIFIED` does not imply more than was preserved.

Acceptance gate:

- [x] Regression for Astra F5 passes: same-second checkpoints and a corrupt newest checkpoint cannot yield silent stale `RESUME STATE VERIFIED`.
- [x] Regression for F7 passes: distinct project names cannot collapse into the same project record.
- [x] Wrong project/clone cannot be reported as fully verified continuation.
- [x] Recovery output states any continuity gap and exactly which revision was recovered.

M3 acceptance evidence: branch `fix/astra-m3-project-recovery`. Regression-first commit `f1c3eba19c637389c88b2700798ce16e363cf0ea` kept foundation verification green while the new M3 gate reproduced five failures in workflow run `35402756411`: no stable project registry, no project-scoped heads, silent stale fallback from a corrupt newest checkpoint, missing revision reporting, and acceptance of a different clone with the same branch/commit. The initial stable-ID and ledger-driven recovery implementation passed all new M3 regressions; inherited compatibility failures were then corrected without restoring slug identity, and the complete suite passed at commit `2ed23952e511edfad74f32dea122081ef2fdc008` (run `35406137151`). Additional migration-collision and dirty/untracked verification-scope gates passed at commit `b6534010694f83808c9da1d0a00d4afa79cceee8` (run `35406215862`). Final audit commit `75b8ccf957e0070ce010baa6845fd1d760647b5e` makes project IDs opaque allocations derived from immutable operation identity/slot rather than display names, rebuilds project registry, per-project heads, and `latest_checkpoint.json` from committed ledger state at writer entry, rejects ambiguous legacy-slug migration, degrades rather than verifies when newer checkpoint state is corrupt or repository working-tree state lies outside the preservation scope, and rejects a different repository location even when branch/commit match. Its full Foundation checks workflow `35406530542` passed.

### M4. Filesystem and Git containment

Goal: Aham cannot mutate outside the selected Brain/project through managed paths, inherited repositories, or tracked private configuration.

Prerequisite: M1 complete. May be implemented in parallel with M2/M3 only if changes do not conflict with the writer design.

- [x] Reject symlinked managed directories and managed path components.
- [x] Verify resolved containment for every controlled write destination.
- [x] Use no-follow/descriptor-relative filesystem operations where supported and document platform limits.
- [x] Require Git top-level identity to match the registered Brain root before Git-transport mutation.
- [x] Refuse or explicitly handle an enclosing unrelated Git repository.
- [x] Detect linked worktrees deliberately rather than inheriting them accidentally.
- [x] Before writing `.aham/runtime.json`, check whether Git already tracks it.
- [x] Verify effective Git ignore behavior, not merely `.gitignore` text.
- [x] Refuse tracked private configuration before mutation and provide safe remediation instructions.
- [x] Audit other machine-local/private files for the same index/ignore failure class.

Acceptance gate:

- [x] Regression for Astra F8 passes: symlinked managed directories cannot redirect writes outside the Brain.
- [x] Regression for F9 passes: Git transport cannot adopt/reconfigure an unrelated parent repository.
- [x] Regression for F10 passes: a tracked `.aham/runtime.json` is detected and refused before private paths are written.
- [x] Containment tests cover path traversal and representative platform-specific path behavior.

M4 acceptance evidence: branch `fix/astra-m4-filesystem-git-containment`. Corrected regression-first commit `0b6d7ba93394abf7fca579e5a03193e322952301` kept foundation verification green while workflow run `35438288857` reproduced all three Astra failures: F8 followed a symlinked `projects/` directory and still reported `WRAP UP VERIFIED`, F9 adopted and reconfigured an unrelated enclosing Git repository, and F10 overwrote a Git-tracked `.aham/runtime.json`. The first containment implementation passed the full workflow at commit `0a4635c5333508d46219600b1635eb68770cb80f` (run `35438491062`). Extended acceptance commit `9edd5007fd9ddbe53ff6e405fcc63ab1d83fc8cf` then reproduced one remaining dynamic-leaf defect in run `35438574769`: a symlinked legacy project file could be migrated and still produce a verified wrap-up. The final containment layer rejects managed directory and leaf symlinks, lexical/absolute escapes, traversal-shaped checkpoint references, unrelated parent repositories, and linked worktrees; it uses no-follow writer-lock/directory opens where available, verifies effective Git ignore behavior, and refuses tracked private runtime configuration before mutation. `docs/FILESYSTEM_CONTAINMENT.md` records the precise guarantee and platform/race limits. Commit `e11f81f6dca6a8ba55ed76b18b297fab1e0696e9` passed the full Foundation checks workflow `35438729368`, including the expanded traversal, linked-worktree, effective-ignore, and symlink gates.

### M5. Enforced session authority and real test isolation

Goal: supported mutation policy is mechanically enforced, and live-agent rehearsals cannot reach real user data merely because they run as the same OS user.

Prerequisites: M1-M4 substantially complete because authority must sit in front of the canonical writer.

- [x] Define a session/controller record binding workspace ID, project ID, allowed operations, runtime/harness identity where relevant, and current revision.
- [x] Require mutation commands to validate session authority rather than trusting startup prose.
- [x] Make read-only/degraded modes mechanically unable to mutate through supported interfaces.
- [x] Give unsupported/untrusted runtime paths a read-only fallback until authority is established.
- [x] Build a disposable OS-enforced rehearsal environment with synthetic Brain/project data.
- [x] Keep real home directory, credentials, SSH agent, container socket, unrelated projects, and real Brain outside writable/readable mounts unless explicitly required.
- [x] Keep the verifier outside the agent's writable trust boundary.
- [x] Add a harmless outside-sandbox sentinel and prove the test agent cannot read/write it.

Acceptance gate:

- [x] Regression for Astra F11 passes: a read-only/degraded session cannot checkpoint or mutate through the supported writer.
- [x] Rehearsal sentinel outside permitted storage is mechanically inaccessible to the agent.
- [x] A successful rehearsal does not depend on trusting the model's statement about permissions or completion.

M5 acceptance evidence: branch `fix/astra-m5-session-authority-isolation`. Session-authority regression commit `79588f34b709e08bb8b4b77f92125aa70927dcf3` kept Foundation verification green while workflow `35441269747` reproduced missing exact-session, stale-revision and harness-identity controls. The first exact-revision implementation exposed its interaction with M2 crash recovery in workflow `35441439628`; the fix moved authority revision advancement to the immutable committed-operation boundary rather than weakening revision equality. Commit `326b265682f6b632eb0a434aa5421bffcb3e0b56` passed the complete workflow `35441527581`, and extended project-binding plus checkpoint/wrap-up/recovery authority tests passed at `fa11d4158e60d798d93c4e0a818d935f625f59a7` in workflow `35441614016`.

OS-isolation regression branch `test/astra-m5-sandbox-regression` at commit `4dffd289f45ba21de498b156117e4836ee62f93e` kept Foundation verification green while workflow `35441878973` failed specifically because the Bubblewrap rehearsal launcher did not exist. After CI-specific namespace restrictions were reproduced and the mechanism was reassessed, commit `e726e7b8dfac0012f0f42dbef738fa054005c9fd` passed workflow `35442180869`: Bubblewrap was installed and exercised, the runtime command ran under the ordinary invoking UID/GID with supplementary groups/capabilities dropped and `no_new_privs`, the real home/SSH agent/container socket/unrelated data were absent, the framework was read-only, and only the synthetic Brain/project were writable. The outside sentinel was mechanically unreadable/unwritable.

The live path then received its own regression. Commit `4276366cac4ba0356286b2bf2b421a3d021cd184` kept Foundation verification green while workflow `35443497670` failed because the live rehearsal had no separate minimal control contract and no sandboxed `run` entry point. Commit `92c496c117919e26513646cfa74b3cc194aa5717` passed the full workflow `35443716908`: the runtime sees only `/control/task.json`, the read-only framework and synthetic workspace/project; the authoritative host manifest and sentinel are absent; in-session task verification uses the minimal read-only contract; checkpoint/wrap-up instructions require the exact startup-issued session ID; and the independent verifier remains outside the sandbox and validates durable artifacts/state rather than model prose. `docs/LIVE_RUNTIME_REHEARSAL.md` documents the Linux/Bubblewrap scope and explicit opt-in escape hatches without broadening the default guarantee.

### M6. Precise success semantics and evidence register

Goal: every success message says exactly what was proven, and release/runtime claims come from one durable evidence source.

Prerequisites: M1-M5 complete enough that receipts can describe real guarantees.

- [x] Replace overly broad success claims with structured receipts containing operation ID, resulting revision, payload digest, accepted item IDs/counts, verification scope, warnings, and recovery action.
- [x] Define distinct wording for local persistence, artifact verification, replicated backup, runtime instruction compliance, and end-to-end recovery.
- [x] Ensure `CHECKPOINT VERIFIED`, `WRAP UP VERIFIED`, and resume output cannot imply unsaved artifacts were preserved when they were not.
- [x] Create one evidence register for live runtime/harness results, including exact model, harness/version, OS, context/quantization when relevant, permission mode, framework commit, rehearsal ID, result, and human intervention.
- [x] Generate README/checklist status from, or mechanically reconcile it against, the evidence register where practical.
- [x] Correct current documentation drift between README and `PROJECT_CHECKLIST.md` before broader testing resumes.

Acceptance gate:

- [x] Receipts survive restart and independently describe committed state.
- [x] Documentation no longer equates framework/profile tests with live runtime behavior.
- [x] Runtime claims have one source of truth and no contradictory manual summaries.

M6 acceptance evidence: branch `fix/astra-m6-success-semantics-evidence`. Receipt regressions at `1eaa21dc784980d8f9e2bf411b170913fefcb71b` and `02f8dd2274ba429a4a5eb236df822d1de8f83168` failed only the intended missing complete/pending evidence behavior before commits `2b4f4c2e80f4de515d6b9bb211fd61990286fe99` and `b265234c0d1f40b2c02407d27549d83a4b25b372` passed the full suite with restart-safe, replay-stable structured receipts. Success-scope regression `3e021f63e039156f709206ae5c8b45cf48d0c4dd` reproduced four overbroad/missing-recovery claims; implementation `f4fdfd1a59301effd8abc0f0a2f6cd5695509c1b` passed workflow `35445942348`, and `docs/EVIDENCE_SEMANTICS.md` defines the distinct guarantee classes. Evidence-register regression `5c896459ce2850aa7dd4b4341eadd16d80cb504a` failed all five intended absent-register tests in workflow `35446209987`; the strict validator and canonical `evidence/runtime_harness_register.json` passed workflow `35446795112`. Live-verifier emission regression `b27bf19979ebc60669bfac2ae71bc68c39629cad` failed because verified reports lacked register-compatible evidence; implementation `f401246172475e572017d18a6871c70ab8a9f15b` passed workflow `35447024699` and emits evidence only after independent verification. Documentation regression `c5a71daea202013758008870f1836ceeace502ab` failed all four intended stale/manual-status checks in workflow `35447121400`; generated register-backed README/checklist status plus reconciled live-rehearsal/test-plan/portability documentation passed Foundation and all 156 unit tests at `efc5d9e0b694be01467bad8f7aeb14c95606bba0` in workflow `35447415695`. Historical unknown metadata remains `null`, framework/profile evidence is a separate type from live-runtime evidence, duplicate live identities and reliability fields are rejected, and one successful run is explicitly only a smoke test.

## Runtime/harness testing resumes here

Only after M1-M6 pass:

- [x] Re-run the same local Qwen path that exposed the earlier failures.

Qwen rerun evidence: rehearsal `037378a6a24347e7` independently verified at `2026-09-19T18:47:37Z` on framework commit `a9921f73fd733fdc696d4cefb5d4c9ba743045d1` using `unsloth/Qwen3.8-27B-GGUF`, DeepSeek Harness `0.1.5-rc.2`, 65,536-token context and `UD-Q4_K_XL`. The trusted wrapper recorded closed stdin and the exact sandbox permission footprint; this remains a single-run smoke test.

- [x] Run the same local model through OpenCode using the same task and comparable context/settings.
- [x] Run the selected model through DeepSeek Harness using the same task and comparable settings.
- [x] Compare harness behavior separately from model behavior.

Harness comparison evidence: DeepSeek Harness rehearsal `037378a6a24347e7` and OpenCode rehearsal `753043981c7d4b1d` both independently verified the same generated live-rehearsal task using `unsloth/Qwen3.8-27B-GGUF`, 65,536-token context, `UD-Q4_K_XL`, closed stdin, shared networking and the same Fedora host OS/kernel. The DSH run used framework commit `a9921f73fd733fdc696d4cefb5d4c9ba743045d1`; the OpenCode run used `5c9fbe3fe5dd91eb7c1176a154dea948e96d76cf`, whose intervening PR #31 changed only retained evidence/documentation rather than rehearsal behavior. The DSH permission record used one extra read-only bind plus one extra read-write bind, while OpenCode used two extra read-only binds and no extra read-write bind, so the sandbox permission footprints were comparable but not identical. Both single runs passed; this comparison does not establish equal harness reliability or a reliability percentage. The same DSH rehearsal is explicitly reused as evidence for the selected-model DSH checklist item rather than performing a redundant second DSH run.

- [x] Include at least one model/harness switch with no prior chat history and recover from durable state only.

Switch recovery evidence: switch `ce20b314417d44af` independently verified at `2026-09-19T20:10:02Z` on framework commit `a9f0be2286a9dfb9ab5d20731d8bcfc6ce4e8bf1`. Runtime A used DeepSeek Harness `0.1.5-rc.2`; fresh Runtime B used OpenCode `1.14.25`; both used `unsloth/Qwen3.8-27B-GGUF`, 65,536-token context and `UD-Q4_K_XL`. The trusted verifier proved Runtime B recovered runtime A's exact committed revision `1`, checkpoint `wrap-switch-source-ce20b314417d44af`, durable fact, unfinished task and project update. The target had closed stdin, a synthetic sandbox HOME, no recognized continuation/attach flag, no user-supplied read-write bind, no source-only contract mount, and runtime A left no marker-bearing project handoff or noncanonical workspace handoff. This is one independently verified switch recovery, not a reliability estimate.

- [x] Include an intentionally malformed request, a denied operation, and an interrupted operation.

Negative-path evidence: rehearsal `d26192c1c816459e` independently verified at `2026-09-19T20:47:07Z` on framework commit `c5be1596dd7b4e3656e68af1fdae36aff6163132`. The trusted controller rejected both the malformed request and denied operation with exit code `1` and zero durable mutation. It then terminated the writer with test-only crash injection at `wrap_up_after_commit_record` (exit `86`) after immutable acceptance of revision `1`. A fresh OpenCode `1.14.25` session using `unsloth/Qwen3.8-27B-GGUF`, 65,536-token context and `UD-Q4_K_XL` recovered the exact accepted revision and checkpoint `wrap-negative-interrupt-d26192c1c816459e`; the independent verifier confirmed the durable fact was conserved exactly once and trusted resume selected the same continuation. This is one negative-path rehearsal, not a reliability estimate or proof that every failure mode is covered.

- [x] Preserve exact evidence in the evidence register; one successful run is a smoke test, not a reliability percentage.

The canonical register now retains the rich Qwen/DeepSeek rehearsal, Qwen/OpenCode rehearsal, fresh-session switch recovery, and negative-path rehearsal as distinct evidence types with their exact verifier-emitted metadata and limitations. Single runs remain explicitly scoped as smoke/rehearsal evidence and are not converted into reliability percentages.

## Should fix before public release

### R1. Compatibility and migrations
- [x] Define Brain/workspace schema version compatibility policy.
- [x] Implement migration runner with explicit forward/refusal behavior.
- [x] Test old, new, unsupported, interrupted-migration, and recovery fixtures.

R1 acceptance evidence: branch `fix/r1-schema-migrations`. Regression-first commit `ea9a0ed5f21f9e27426d90958ecd9e67fa37e0bd` preserved green Foundation verification while workflow `35469695684` failed only the seven new compatibility/migration expectations. The implementation separates immutable `BRAIN.json` identity-envelope versioning from mutable workspace-state schema versioning so existing workspace fingerprints and historical operation/checkpoint identity are not rewritten. Pre-R1 workspaces without `state/schema.json` are explicitly schema 0; new workspaces are schema 1; newer/unknown schema is refused rather than guessed. `scripts/migrate_workspace.py` performs the tested 0→1 transition with pending-state recovery and durable completion receipts, including an injected exit-86 interruption after the schema write. The first full implementation run exposed that Git durable snapshots omitted the new schema manifest; an added regression required `state/schema.json` to survive transport, while completed migration receipts became durable and `state/pending_migration.json` remained excluded. Commit `33db43cb56a42bdacaec061e06fabb13a21103fd` then passed Foundation verification and all 187 tests in workflow `35470076465`. `docs/SCHEMA_COMPATIBILITY.md` records the compatibility and refusal policy.

### R2. Fact and task lifecycle
- [x] Give durable facts stable IDs and provenance.
- [x] Support supersede/retract without deleting history.
- [x] Give tasks stable IDs and explicit open/completed/cancelled transitions.
- [x] Preserve conflicting sources explicitly rather than flattening them into one statement.

R2 acceptance evidence: branch `fix/r2-fact-task-lifecycle`. Regression-only commit `30bd86c8e6dc257a5604a336ece1d49891149599` kept Foundation verification green while workflow `35471100539` failed exactly the seven new lifecycle tests and left all prior 188 tests passing. `scripts/record_lifecycle.py` reconstructs a structured lifecycle view from the immutable operation ledger rather than creating a second mutable fact/task database. Wrap-up facts/tasks receive deterministic stable IDs and provenance; lifecycle operations preserve superseded/retracted facts and completed/cancelled tasks, retain explicit conflict links and source provenance, reject invalid second transitions without revision advance, reuse exact retries, reject conflicting retries, and remain mechanically denied to degraded/read-only sessions. The first integrated run exposed only a request-normalization defect; commit `593124f177c3c38d19d21128fa96f0ea85e65fcb` corrected it and passed Foundation plus all 195 tests in workflow `35471568872`. Final integration simplified the ledger change to one explicit operation-kind set in `state_store.py`; commit `3ff3c41eddda04fb318144941f33462fd3bd80c7` again passed Foundation plus all 195 tests in workflow `35471736943`. `docs/FACT_TASK_LIFECYCLE.md` records the lifecycle, provenance, authority and idempotency semantics.

### R3. Compact context assembly and conformance tiers
- [x] Produce bounded project-scoped context packets from authoritative revisions.
- [x] Avoid requiring low-context models to browse the entire Brain.
- [x] Define runtime/harness conformance tiers based on demonstrated capabilities.
- [x] Run the selected conformance matrix within documented context/cost limits.

R3 acceptance evidence: branch `fix/r3-context-conformance`. Regression-only commit `4fa54682508af386acb114218e40706014d6e812` kept Foundation verification green while workflow `35472267636` left all prior 195 tests passing and failed exactly the seven new R3 expectations because bounded project packets, capability tiers and matrix tooling did not yet exist. The initial implementation head `eaefcff347181fb6afa5428d4bf9e4e48a214a7c` added `scripts/context_packet.py`, vendor-neutral `core/runtime_conformance.json`, and retained-evidence matrix tooling; workflow `35472445936` passed Foundation plus all 202 tests. Final diff review then found two concrete integrity gaps: legacy fact/task records from a multi-project wrap-up could be fanned into every project packet, and checkpoint assembly checked revision but not full checkpoint/workspace validity. Regression commit `df7b9e06033ebc4e124afd6634f9ca60d458b993` kept Foundation green and failed exactly those two added tests while the previous 202 remained green. Commit `ddf83e95ee1945bbcc88bdda8538a179e48d7c28` fixed both by omitting ambiguous unscoped records and validating checkpoint schema, workspace identity, revision and project binding; workflow `35472733420` passed Foundation plus all 204 tests. `docs/CONTEXT_CONFORMANCE.md` records project-scope rules, deterministic byte budgeting with no token-equivalence claim, integrity checks, vendor-neutral tiers and the evidence boundary; its first documentation commit `9c4614f882def850540d2608b414e7a51849eabb` passed Foundation plus all 204 tests in workflow `35472841802`. A final conformance-scope regression at `d9deab911f356dbd279c591a050900de1d99364f` proved that recovery evidence for one model could incorrectly upgrade a different model merely because the harness/version matched; workflow `35473029764` failed only that added test while the prior 204 remained green. Commit `ab46ade9402a1db6b247bdab33cd88a798fd56b0` binds recovery tier evidence to the exact harness version, model, context and quantization configuration and passed Foundation plus all 205 tests in workflow `35473134253`. The selected matrix reuses retained independently verified DeepSeek Harness/OpenCode lifecycle/recovery evidence and requires zero new live runs; the documentation explicitly states those historical runs predate `context_packet.py` and therefore do not prove live packet consumption.

### R4. Backup/export/restore
- [x] Define portable export independent of semantic-memory provider.
- [x] Verify restore into a clean location/machine.
- [x] Compare record/artifact manifests after restore.
- [x] Distinguish local durable save from replicated backup.

R4 acceptance evidence: branch `fix/r4-portable-backup-restore`. Regression-first baseline `2ba49ff7a17a167e1f4b6fbe25b6830116048742` established deterministic provider-neutral export, clean restore, manifest comparison, corruption/refusal, transient-state exclusion, and backup-claim expectations. Implementation `3ff8881b28afb0539a028385422fe59c9da3b4be` added the explicit `core/portable_backup.json` contract and `scripts/portable_backup.py`. Restore verification exposed omitted-but-required empty structural directories; commit `589b5463be5e39ff0519000d47dba392272eb565` corrected that and workflow `35474490326` passed Foundation plus all 212 tests. Writer-coordination regression `c5eed9bc2e4c74216bd3720c9e715d61259d4753` then proved export could complete while the authoritative workspace writer lock was held; workflow `35474650371` failed only that new expectation. Commit `7389e05612142bebd70be98d99fbb7e81f30226b` reuses `state_store.writer_lock` across manifest creation, copying, verification and publication. A final containment audit proved restore already rejects a destination inside the public framework repository; only the new regression's expected wording required correction at `8b619deecdec8058ac3d6dfc91c6f7a353318535`. Exact-head workflow `35474968324` at checkpoint commit `53e4a8cbfac08f79cef236190fd0ee8a06bee73b` passed Foundation plus all 214 tests. The tested restore target is a clean temporary workspace on the GitHub-hosted Ubuntu runner; this R4 evidence does not claim Windows/macOS portability, which remains R5. `docs/PORTABLE_BACKUP_RESTORE.md` records that a portable export is provider-independent local state, not proof of replication, and that unkeyed SHA-256 verifies payload integrity relative to the manifest rather than authenticating a bundle against an attacker who can alter both manifest and payload.

### R5. Platform and Git-environment hardening

- [x] Declare supported Python/platform range.
- [x] Test Linux plus intended macOS support before claiming portability; Windows durable mutation remains unsupported.
- [x] Test spaces, Unicode, case-insensitive collisions, worktrees, detached heads, permissions, inherited Git config, hooks/filters, and subprocess timeouts.
- [x] Add crash/recovery testing for external-source activation.

R5 acceptance: exact head `c480e00073416f254493bfc218a6de1516200e51`, hosted
workflow `36861543247`, all six jobs executed and passed. Linux Foundation ran
231 tests; Linux/macOS Python 3.10/3.14 each ran 196 portable tests. macOS jobs
each skipped two tests. Windows Python 3.14 passed Foundation and native
unsupported-lock refusal without workspace mutation. This does not claim native
Windows lifecycle support, maintainer-owned Mac evidence, physical power-loss
certification or support on removable/network/cloud-synced storage. Added tests
cover four fresh-process activation crash boundaries, case/accented project
heads and immutable-publication refusal. Supplementary triage and filesystem
limits are in `docs/dev/R5_TODO.md` and `docs/STATE_WRITER.md`.
PR #43 merged with an expected-head guard as `4a3b0d47c98aa354ef64f14f2e78bf1abbea4989`.
Historical infrastructure details still require the pre-publication human review.

### R6. Semantic retrieval and external activation scope
- [x] Ensure semantic retrieval respects project/client scope and current fact state.
- [x] Ensure retracted/superseded facts are filtered or clearly labeled.
- [x] Bind activated external content to reviewed/scanned identity and detect drift.

R6 merged through PR #48 as `63d5fcf22e55c93b11fc3dfdeba44bb38dba1651`.
Exact tested implementation: `eddff878b2ab328ae1527ee901b5ec539bcd6901`.
Workflow `36866478419` passed full Linux (248 tests), Ubuntu/macOS Python
3.10/3.14 portability (213 tests per job, two skips per macOS job), and native
Windows unsupported-write refusal. Red baseline `e16ed7e` in workflow
`36863810011` failed exactly the 11 new assertions. Seventeen R6 regressions cover
identity/mismatch, drift and legacy/report exclusion, scopes, escaped output/errors,
same-commit recovery, mutation during publication, aliases, bounds and authority/
receipts. Fresh-process crash coverage includes the activation operation record.

At R6 completion, all recall was explicitly unverified pending S4 record mapping;
provider text cannot assert current/superseded/retracted state. Scoped adapter
wake-up uses wing-filtered search because pinned native wake-up includes global
identity. S2 must use the verified usable-source list. POSIX freezing guards
accidental edits; an owner can undo it. Existing semantic configuration transactions
and custom project-wing mappings were then deferred to S4, now complete below. No Windows lifecycle or physical
power-loss guarantee is added by this gate.

### R7. Nontechnical usability
- [ ] Fresh user completes setup without architecture knowledge.
- [ ] Fresh user performs a model/harness switch using durable state.
- [ ] Fresh user recovers from an interrupted operation using diagnostics.
- [ ] Diagnostics provide concrete next action without falsely claiming readiness.

Implementation checkpoint PR #61 merged as
`758be6478b2fc5a06bf30a898b9eaa300e9791a2`. Exact head
`94f88d1053c9479606b25ec9ed2ca2cc9997ab27` passed six jobs in workflow
`36915089427`: 390 Linux tests, 355 per Ubuntu/macOS Python 3.10/3.14 job
(two skips per macOS job), and Windows unsupported-write refusal. Eighteen
synthetic R7 regressions and the full local suite passed. This evidence verifies
controller behavior, not newcomer success; all four human gates remain open.
See `docs/R7_TEST_DESIGN.md` and `docs/dev/WALKTHROUGH_PROTOCOL.md`.

## Product completion before public release

Controlling order: R6 -> S1 -> S2 -> S3 -> S4 -> A1 -> R7 -> W1 (per D3) -> R8.
Implementation through W1 and R8 repository preparation is merged. R7 real human
walkthroughs and final R8 publication gates remain open. E1's live Claude run is
deferred by the maintainer; unlisted-runtime/paste-mode evidence remains open.
The gates below are copied from `docs/PUBLIC_RELEASE_PLAN.md`.

### S1. Skill scanner v2: prompt-injection and execution-surface safeguards

- [x] every fixture produces its expected verdict; no fixture in a FAIL category ever receives PASS; existing scanner and supply-chain tests still pass; waiver invalidation test passes; report renders in plain language; Superpowers false-positive result recorded.

S1 merged through PR #50 as `4e2d68ad13cefc927539ae7a68063bc72a282270`.
Exact implementation `de9c1eaec9de42ee2cbfcec7337c186fbc0cc660` passed all six
jobs in workflow `36873888390`: 273 full Linux tests, 238 tests per Ubuntu/macOS
Python 3.10/3.14 job (two skips per macOS job), and Windows unsupported-write refusal.
Draft Linux workflow `36873457417` also passed. Original hosted baseline
`36867861182` failed exactly 18 new assertions; further local regressions preceded
implementation. The final suite adds 25 S1 tests. D5/D6 are opt-in as approved.
The pinned Superpowers rehearsal passed its lifecycle and correctly blocked a FAIL
scan; all 160 findings are accounted for in `docs/S1_SCANNER_EVIDENCE.md`. Potential
context false positives were unresolved at S1 completion. S3's tested corrections
are recorded below, with no agent waivers. PASS remains a heuristic result.

### S2. Skill index and universal activation

D4 approved: universal file-reading bridge first; native loader copies are deferred.

- [x] fixture skill installed then listed; context packet stays within budget; disabled and drifted skills absent; read-only session cannot enable or disable; bridge text test confirms the new rules.

S2 merged through PR #52 as `74633e0ad7874696388bb199e0a47d57638af5db`.
Exact corrected head `476222da518776a2cde714523bbbf185c2387f97` passed all six
jobs in workflow `36879782673`: 286 full Linux tests, 251 tests per Ubuntu/macOS
Python 3.10/3.14 job (two skips per macOS job), and Windows unsupported-write refusal.
The original seven-case baseline `36875603316` ran 280 tests and failed exactly
two assertions and five missing-module errors. Expanded local cases preceded their
implementation; the final suite has 13 S2 tests. Initial head `1be1baa` passed
Linux `36877889562`; matrix `36878736815` exposed a macOS temporary-directory alias.
A local POSIX alias test reproduced it before canonical-root normalization. Only
one corrected-head matrix was run. Reads ignore cache claims and derive skills from
committed activations/current identity and ledger preferences. Broken optional
metadata or mismatched revisions cannot inject skills or block core project context.
This is framework evidence; native copies and live-runtime consumption are deferred.

### S3. Skill lifecycle and updates

- [x] each command tested with synthetic local Git repositories (the existing test pattern), including rollback after a failed update and crash during rollback.

Scanner checkpoint PR #54 merged as `5c1723a78b01af8156a3fbdc705b091181f8d62d`;
exact head `9dff88db264eadabea07bc9c7c037d9e14e41fe6` passed all six jobs in
`36883836912` (294 full Linux tests, 259 per portability job). The unchanged pin
now has 98 REVIEW and two INFO findings, with activation still blocked and no
accepted findings. D8: review Superpowers first; defer more defaults.

Lifecycle PR #55 merged as `8c76a10f779f7a9025b33e8805ab4a1cf45a320e`.
Exact implementation `d748ca4cb9c9a68ea6afd0dd940964940ea68811` passed all six jobs
in workflow `36897056292`: 314 full Linux tests, 279 per Ubuntu/macOS Python
3.10/3.14 portability job (two skips per macOS job), Windows unsupported-write
refusal. Local red preceded 20 lifecycle regressions; a final historical archive
payload failure was reproduced and fixed locally before this one ready matrix.
Rollback covers all five activation crash boundaries; removal covers four
deactivation boundaries in fresh processes. Archive identity/path/payload checks,
concurrent update refusal, local provenance, exact synthetic finding confirmation,
advisory preservation and read-only refusal passed. No real finding was accepted,
no files deleted and no hooks or provider installed. Scheduled polling is deferred.
The lifecycle matrix used 470 summed runner seconds, or 11 per-job rounded minutes;
the scanner matrix used 520 seconds/13 rounded minutes. Neither is billing usage.
Contracts and evidence: `docs/SKILL_LIFECYCLE.md`, `docs/SOURCE_REVIEW.md`,
`docs/S3_TEST_DESIGN.md`, `docs/S3_SOURCE_REVIEW_EVIDENCE.md`.

### S4. MemPalace connection v2

- [x] fake-provider tests for scope enforcement, envelope, index-lag reporting, failure isolation, and no write without opt-in; re-review evidence recorded in the registry.

S4 merged through PR #57 as `47c32ed8fee5b44cd4743bc6e8e2c1f7042bc4e1`.
Exact tested implementation `d406545418337764e68bd9c4af28337272e978d1`
passed all six jobs in workflow `36904820142`: 343 full Linux tests,
308 per Ubuntu/macOS Python 3.10/3.14 portability job (two skips per macOS job),
and Windows unsupported-write refusal. Local acceptance passed 343 tests with
one expected skip; the S4 module has 29 regressions.

Initial matrix `36903749610` passed Linux/Windows but both macOS jobs exposed
process-group cleanup refusal after provider exit. A local injected-permission
regression reproduced both exited-parent and timeout cases before the fix.
Initial/corrected matrices used 538/535 summed runner seconds, or 11/11 per-job
rounded minutes; these are runner measurements, not billing usage. No hosted red
baseline, draft gate, blind retry or live personal-data ingestion was used.

Configuration and progress use the immutable writer ledger and receipts. Project
wings are unique, indexing requires opt-in/write authority, and optional indexing
cannot invalidate a committed wrap-up. Catalogs use one verified ledger snapshot;
exact current bindings are matched, inactive records are stale, foreign stamps
are omitted and other provider prose remains unverified. D10 is approved: offline
keyword recall is included. Stable staging is excluded from Git/portable exports.
Command progress is provider-reported evidence, not durable ingestion proof.

Public MemPalace link pin is `f8b9ed1507888cab47c7c7e1d90755f89e0353c4`.
Both whole-tree scans remain FAIL, with no finding acceptance or source activation.
Registry approval covers the independently installed CLI interface only. Evidence:
`docs/MEMORY_CONNECTION.md`, `docs/S4_TEST_DESIGN.md`,
`docs/S4_SOURCE_REVIEW_EVIDENCE.md`, and the retained finding inventory.


### A1. Any-assistant access

- [x] an unlisted runtime name becomes writable only after trust plus self-test; trust can be revoked; degraded mode stays read-only; paste-mode round trip passes; malformed paste is rejected with zero mutation; instruction byte budget test passes.

PR #59 merged as `c739ad61a359c1d884b21588fe6c71fd4cb70c39`; exact tested head
`7fa757496bc293062031d1013223a65cfdd0b689`, workflow `36909749861`, all six
jobs green (372 Linux, 337 portable per job, two skips per macOS job, Windows
refusal). Local regression-first design and final 29-case coverage are in
`docs/A1_TEST_DESIGN.md`; the owner and chat workflows are in
`docs/ASSISTANT_ACCESS.md`. Trust records are canonical; probes/caches are transient.
No native Windows or live chat consumption is claimed. R7 is next. D9 owner-only
POSIX permissions and D3 native Windows implementation have explicit owner approval.

### W1. Windows support (per D3)

Maintainer authorized proceeding with W1 on 2026-10-01 while R7's external
human walkthroughs remain pending. Their acceptance boxes stay open.

- [x] the Astra F4 independent-process concurrency regression passes on Windows; the portability suite is green on a hosted Windows runner; `docs/PLATFORM_SUPPORT.md` updated with exact scope.

PR #64 merged as 3a5f139a3ac730ee5a19b6b51faa7a95d16ece0d. Exact head 1027f70c9c9d62f8edcb849c338feac20eea15c8 passed all six jobs in workflow 36936673766: 407 Linux tests (four skips), 372 per Ubuntu/macOS portability job (four Ubuntu/six macOS skips), and 372 native Windows core tests (nine skips) plus six independent-process concurrency/recovery tests. Windows Python 3.14.7 on the hosted local filesystem passed protected ACL creation/drift, long paths, junction refusal and literal PowerShell execution. The matrix used 997 summed runner seconds, or 20 minutes rounding each job up; these are measured runner times, not billing usage.

### E1. Runtime evidence follow-ups

- [ ] Record Claude live rehearsal, an unlisted-runtime trust-flow run and a chat paste-mode run; measure bridge/startup bytes after A1. Single runs remain smoke tests.

### R8. Publication audit

Repository preparation merged through PR #66 as
`8ce128b226edde8a069bd0df9c50eb934fa184a6`. Exact saved head
`68bfb593831b68a143c182a66ee27c35c635d13f` passed workflow `36938429399`:
412 full Linux tests (four skips), Foundation and offline release rehearsal.
Stable local acceptance passed 412 tests (five skips) in 101.208 seconds.
Five local red policy tests preceded implementation; no hosted red gate or
duplicate portability matrix. W1's platform implementation is unchanged.
Contributor Covenant 2.1 by-reference policy and its reporting contact are approved.
Preparation does not close the human, final-tree provenance or publication gates.

- [x] Prepare contributor/security/release materials and verify hardened CI.
- [x] Prepare a verified maintainer settings checklist without applying settings.

- [ ] Run automated release checks on the actual release tree.
- [ ] Perform final human privacy/history review.
- [ ] Verify runtime/test claims against retained evidence.
- [ ] Complete provenance commitment only for the final reviewed tree.
- [ ] Maintainer explicitly authorizes public release.

## Useful later, not current work

- [ ] Additional harness adapters after the common conformance contract is stable.
- [ ] SQLite or another backend only if measured scale/transaction requirements justify it; retain portable export.
- [ ] Read-only history/recovery viewer or local setup UI.
- [ ] Incremental semantic indexing and retention/archival tooling after correctness is stable.
- [ ] Multi-machine replication with explicit conflict handling.
- [ ] Team/shared workspaces only after a separate multi-user permission design.

## Preserve these design principles

Do not "fix" the architecture by removing these properties:

- [x] User-owned, inspectable durable state and a portable export path.
- [x] Separation among public framework, private Brain, and project repositories.
- [x] Local operation without mandatory cloud, Git host, semantic-memory provider, or skill loader.
- [x] Vendor/model-neutral core and honest unknown-runtime limitations.
- [x] Third-party provenance, quarantine, attribution, and separate permissions.
- [x] Preservation of unrelated user files/instructions.
- [x] Independent verification and small recoverable milestones as core goals.

## Completion definition

Architecture remediation is complete when, after any accepted operation, exact retry, conflicting retry, supported interruption, or supported model/harness switch, a fresh trusted reader can state exactly:

1. what revision is committed;
2. what information and artifacts are actually preserved;
3. what remains pending or unpreserved;
4. what authority/session performed the mutation;
5. what evidence supports each success claim.
