# Aham Brahmasmi architecture review

Date: 2026-09-18  
Reviewed implementation: `a94f2a79242ee835b90b6d68bbb2a298bd80d035`  
Review branch: `review/astra-architecture-2026-09-18`  
Status: Complete. All 32 questions answered, with reproduced findings, source references, test results, and a prioritized plan.

## Architectural verdict

I would preserve the public framework/private Brain separation, readable local state, optional Git and semantic memory, and vendor-neutral lifecycle intent. I would change the central enforcement architecture before expanding runtime support: put persistence, operation identity, recovery, and verification behind a small authoritative state writer. Treat models as fallible request producers.

The current implementation has useful defensive machinery, including atomic file replacement, unique workspace identity, pending transactions, explicit recovery, and rejection of unknown new-bundle fields. However, its success statements are stronger than its guarantees. A file or marker can exist while the intended information is missing, stale, or contradictory. Improving prompts alone cannot repair that mismatch.

No implementation files were changed. The probes below used disposable workspaces outside the repository. They did not use a real private Brain or invoke additional models for runtime rehearsals. Findings describe the pinned implementation, including the recent wrap-up schema fix.

Scope covers the repository's lifecycle/state helpers, setup and verification, runtime profiles and bridges, semantic adapter, Git transport, external-source installation/scanning, release and live-rehearsal tools, provenance tooling, core contracts, templates, policies, CI, and tests. This is an architectural and behavioral review of that source snapshot, not a certification of upstream products, repository-history privacy, or every possible exploit. Repository-recorded live results are identified as such. Proposed interfaces and migration mechanisms below are recommendations, not claims that they already exist.

## Reproduced findings

Severity: P1 means a correctness or containment issue that should block broader testing with valuable state. P2 means a significant reliability or usability gap. These are architectural review priorities, not claims of remotely exploitable vulnerabilities.

### F1. P1: Reusing a session ID can report success while discarding new routed content

**Reproduced through the CLI.** Wrap up a bundle with `session_id: reused`, fact `original fact`, and checkpoint summary `first`. Submit a second bundle with the same session ID, fact `replacement fact`, and summary `second`.

Both invocations return exit code 0 and `WRAP UP VERIFIED`. `MEMORY.md` retains only `original fact`. The archived transaction now contains `replacement fact`, and the checkpoint describes `second`. The durable record contradicts itself.

The cause is marker-only idempotency in [`scripts/state_io.py:128-136`](../../../scripts/state_io.py), marker-only route verification in [`scripts/wrap_up.py:290-294`](../../../scripts/wrap_up.py), and unconditional overwrite of the checkpoint and archive for a reused identifier. Completion verification compares selected metadata but not the full routed payload.

**Required change:** Bind an immutable operation ID to a canonical payload digest. An exact retry returns its existing receipt. The same ID with different content must fail before mutation. Validate destination content against the accepted payload, not merely marker presence. Never overwrite an accepted operation's historical record.

### F2. P1: Content can impersonate the marker used as persistence evidence

**Reproduced through the CLI.** Submit two facts under session `quoted`. Let the first fact contain the literal text `<!-- aham:quoted:memory:1 -->`; let the second be `important second fact`.

Wrap-up returns exit code 0 and `WRAP UP VERIFIED`, but the second fact is absent from `MEMORY.md`. The first fact's quoted marker causes `append_marked_block` to skip the real second entry. The verification loop accepts the same quoted marker as proof.

This does not require a malicious model. A lesson explaining Aham's markers could include such text. See [`scripts/state_io.py:128-136`](../../../scripts/state_io.py) and [`scripts/wrap_up.py:290-294`](../../../scripts/wrap_up.py).

**Required change:** Keep authoritative operation identity outside free-form Markdown. Generate Markdown from structured accepted records, or use an unambiguous parsed representation with independently verified content hashes. User content must never satisfy control metadata checks.

### F3. P1: Pending recovery bypasses the new bundle's strict normalization

**Reproduced with a deliberately altered pending fixture.** Create a valid pending transaction, replace its canonical `durable_facts` field with the supported input alias `facts`, then invoke `--recover-pending`.

Recovery reports `WRAP UP VERIFIED` with exit code 0, but the fact never reaches `MEMORY.md`. New requests call `normalize_bundle`; recovery reads JSON directly. `apply_transaction` treats absent canonical fields as empty and does not reject unexpected fields. The alias remains in the archive, but normal routed memory omits it.

This probe demonstrates the acceptance gap for damaged, hand-edited, migrated, or externally produced pending records. It does not claim the current new-request path normally writes that malformed fixture. See [`scripts/wrap_up.py:147-185, 235-260, 382-394`](../../../scripts/wrap_up.py).

**Required change:** Validate persisted transaction envelopes and their canonical payloads on every recovery. Pending state should have a strict versioned schema, a payload digest, and explicit migration rules. Input aliases belong at the request boundary; malformed persisted state must not be silently interpreted as an empty category.

### F4. P1: Concurrent appends can lose an accepted entry

**Reproduced with a controlled interleaving of the existing helper.** Two threads call `append_marked_block` on the same fixture. A barrier before `atomic_write_text` makes both finish reading the old file before either replaces it. Both calls return `True`; the final file contains only one entry.

This is a deterministic test of the read-modify-write race, not a claim that a stress test of two complete wrap-up processes was run. Atomic replacement prevents a torn individual file; it does not prevent lost updates. The check for an existing pending transaction is also a check-then-write sequence without exclusive acquisition. See [`scripts/state_io.py:128-136`](../../../scripts/state_io.py) and [`scripts/wrap_up.py:389-394`](../../../scripts/wrap_up.py).

**Required change:** Serialize writers for a Brain and require an expected state revision. Acquire the writer lock before checking pending state. Include checkpoint and Git snapshot operations in the coordination design. A second writer must wait or receive an explicit conflict; it must not overwrite the first writer's input or progress.

### F5. P1: Resume can select an older checkpoint while reporting verified state

**Reproduced in two cases using helper-generated fixtures with controlled timestamps, then the actual resume CLI.** First, create two valid checkpoints within the same timestamp second, named `zz-first` and `aa-second`, in that order. The latest pointer correctly references `aa-second`; resume chooses `zz-first` and reports `RESUME STATE VERIFIED`.

Second, create checkpoints in consecutive seconds and corrupt the newest JSON file. Resume silently skips it, chooses the older checkpoint, returns exit code 0, and reports verified state with no warning about lost recent continuity.

`utc_now` truncates to seconds. Selection sorts by timestamp and filename, not commit order, and skips invalid files. Resume does not consult the latest pointer. See [`scripts/state_io.py:30-31, 241-264`](../../../scripts/state_io.py) and [`scripts/resume.py:43-51, 78-90`](../../../scripts/resume.py).

**Required change:** Use committed monotonic sequence numbers within the writer's serialization scope. Treat the latest pointer as an index to reconcile against authoritative committed records. Explicitly report damaged or missing newer records. Recovering an older verified record is useful, but it must be labeled degraded recovery with a stated gap.

### F6. P2: Retry safety depends on the caller retaining an optional identifier

**Reproduced through the CLI.** Submit the same bundle twice without `session_id`. Both succeed; the same fact appears twice. Each normalization generates a new random ID ([`scripts/wrap_up.py:154-159`](../../../scripts/wrap_up.py)).

A model may repeat a command after losing its terminal result or after a context reset. Byte-identical requests are then indistinguishable from intentional new operations.

**Required change:** Allocate and persist the operation ID before execution, expose it in a request receipt, and give the caller a retry/status operation. Do not globally deduplicate equal prose: identical text can represent legitimate separate events.

### F7. P2: Different projects can route to the same document

**Reproduced through the CLI.** Project names `a/b` and `a b` both route to `projects/a-b.md`; wrap-up reports verified success with both projects merged into that file. Names longer than 80 normalized characters can also collide. Case-insensitive filesystems introduce additional ambiguity.

See [`scripts/state_io.py:139-143`](../../../scripts/state_io.py) and [`scripts/wrap_up.py:265-274`](../../../scripts/wrap_up.py).

**Required change:** Allocate stable project IDs and store display names separately. Resolve the selected project explicitly; never use a lossy filename slug as its identity. Detect collisions during migration.

### F8. P1: A verified workspace can route writes outside its root

**Reproduced through the CLI.** Replace a disposable workspace's `projects/` directory with a symlink to an unrelated fixture directory. `verify_workspace.py` returns `WORKSPACE VERIFIED`. Wrap-up writes `demo.md` in the unrelated directory and reports `WRAP UP VERIFIED`.

Workspace validation checks that expected paths are files/directories but follows symlinks. Atomic replacement under a symlinked parent still writes outside the selected Brain. See [`scripts/state_io.py:48-80, 102-118`](../../../scripts/state_io.py), [`scripts/verify_workspace.py:43-57`](../../../scripts/verify_workspace.py), and [`scripts/wrap_up.py:270-274`](../../../scripts/wrap_up.py).

**Required change:** Validate containment for every controlled path component and reject symlinked managed directories. Use descriptor-relative, no-follow operations where supported, with an explicit platform policy. Filesystem checks reduce mistakes; they cannot contain an agent that has unrestricted access to the same host. Rehearsals need OS-enforced isolation as well.

### F9. P1: Git transport can adopt and reconfigure an unrelated parent repository

**Reproduced through the CLI.** Initialize a disposable parent Git repository, create a Brain in a child directory, and run Git transport `init` with a fixture author identity. The command reports `GIT TRANSPORT INITIALIZED`; no Brain-local repository exists, and the parent's local author configuration has changed.

`is_repo` asks only whether the directory is inside a worktree. It does not require the Git root to equal the Brain root. `configure_identity` then operates on the inherited repository. See [`scripts/git_transport.py:100-102, 157-162, 181-205`](../../../scripts/git_transport.py).

**Required change:** Require the resolved Git top level to match the registered Brain root before any transport mutation. Handle linked worktrees explicitly. Refuse an enclosing repository with a clear diagnosis. Also make setup warn when the chosen Brain location is nested in an unrelated repository, since another tool could later stage it accidentally.

### F10. P1: The bridge's Git-ignore claim is not verified against Git

**Reproduced through the CLI.** Stage a placeholder `.aham/runtime.json` in a disposable project, then install the Codex bridge. Installation overwrites that tracked file with local framework, workspace, and project paths. Installation says it is Git-ignored, and status reports `local_config_ignored: true`. `git ls-files` still lists it.

An ignore pattern does not untrack an existing file. Both installation and status inspect only the ignore file's text. See [`scripts/runtime_bridge.py:142-151, 253-266, 294-297`](../../../scripts/runtime_bridge.py).

**Required change:** Check the Git index before writing private configuration and verify effective ignore behavior. Refuse tracked private configuration before mutation; explain remediation without silently rewriting user history. An existing unmanaged config also deserves ownership validation before replacement.

### F11. P1 architectural gap: Runtime write policy is descriptive rather than enforced

**Reproduced through separate CLI calls.** Startup in `degraded_offline` reports `core_allows_writes: false`. An immediate checkpoint call for the same Brain still returns `CHECKPOINT VERIFIED`.

This is not an OS sandbox escape: the scripts do not claim to establish an OS sandbox. It demonstrates that the lifecycle's no-write rule has no mechanical continuity between startup and mutation. Capabilities are explicitly caller-reported, and mutators receive no session authority, expected revision, or mode. See [`scripts/startup.py:143-200`](../../../scripts/startup.py) and [`scripts/checkpoint.py:45-59`](../../../scripts/checkpoint.py).

**Required change:** A controller should establish a session with workspace/project identity, permitted operations, and revision. The writer validates that authority on each mutation. Unsupported runtimes receive a read-only interface until authority is established. Prompt instructions remain guidance, not permission enforcement.

## Additional findings from source inspection

These are design risks supported by source inspection, not additional reproduced failure claims.

- **Checkpoint scope is narrower than the user promise.** `git_snapshot` records name, branch, and HEAD only. It neither captures nor rejects dirty/untracked work. A checkpoint can verify its own JSON while the actual artifact remains unsaved elsewhere. Resume checks ancestry and branch, not stable project identity or artifact contents. See [`scripts/state_io.py:159-172`](../../../scripts/state_io.py), [`scripts/checkpoint.py:31-42`](../../../scripts/checkpoint.py), and [`scripts/resume.py:53-76`](../../../scripts/resume.py).
- **Crash consistency stops at individual file replacement.** The writer fsyncs the temporary file but does not fsync the parent directory after rename. Wrap-up spans several independently replaced files. A power-loss guarantee needs documented filesystem assumptions, directory synchronization where supported, and a committed operation record distinct from projection progress. See [`scripts/state_io.py:102-125`](../../../scripts/state_io.py).
- **Bridge installation is several writes without a transaction.** It changes ignore rules, shared bridge text, local configuration, then native instructions. A crash or failed final write can leave these out of agreement. Installing another runtime rewrites shared runtime configuration; earlier native instruction links remain. These should share neutral project configuration and have separate runtime bindings. See [`scripts/runtime_bridge.py:218-274`](../../../scripts/runtime_bridge.py).
- **External-source activation has exception rollback, not crash recovery.** The installer moves the old source aside, moves the replacement into place, and writes the manifest. Its exception handler can roll back Python failures, but process death between those operations has no durable recovery journal. The already-installed shortcut trusts the manifest ref plus directory existence without checking current source contents. See [`scripts/third_party.py:251-305`](../../../scripts/third_party.py) and [`scripts/external_sources.py:103-130`](../../../scripts/external_sources.py).
- **Git execution policy is inconsistent.** Brain snapshot commits deliberately suppress hooks, and initialization uses an empty template. External-source fetch instead performs ordinary `git init` and checkout, inheriting environment/configuration behavior. Review hooks, filters, URL rewrites, credential helpers, and subprocess limits as explicit executable trust inputs. A reviewed commit does not certify the local Git execution environment. See [`scripts/git_transport.py:57-79, 184-196`](../../../scripts/git_transport.py) and [`scripts/third_party.py:171-203`](../../../scripts/third_party.py).
- **The scanner correctly disclaims semantic safety.** Preserve that honesty. Its `PASS` means a limited structural scan, not that a skill is safe to obey or execute. Scanning has no whole-tree content digest in the report; Git cleanliness is checked separately. Keep review, content identity, scanner result, and execution permissions distinct. See [`scripts/scan_external.py:35-127`](../../../scripts/scan_external.py).

## Test and evidence assessment

Executed against the reviewed implementation with only this review document added:

```text
python3 tests/verify_foundation.py
FOUNDATION CHECKS PASSED

python3 -m unittest discover -s tests -p 'test_*.py'
Ran 86 tests
OK (skipped=1)
```

The foundation scan passed and 85 tests passed; one test was skipped. The review's 12 disposable probe cases support F1-F11, with two distinct cases under F5. The concurrent-append probe deliberately controlled scheduling, and the pending-alias probe deliberately supplied an altered persisted fixture. No power-cut test, live model session, external-source network installation, or multi-machine synchronization test was run for this review. The existing suite includes an offline release rehearsal.

The suite has real value: it executes CLI subprocesses, uses actual temporary Git repositories, tests schema rejection and alias conflicts, preserves existing instruction content, tests source tampering before activation, and checks recovery diagnostics. It is more useful than a suite consisting only of mocked helpers.

Documentation already shows some drift: README lists Gemini and Codex live rehearsals as remaining gates, while `PROJECT_CHECKLIST.md` records passes for those two on 2026-09-18. Keep release claims tied to one evidence register instead of maintaining parallel status summaries by hand.

Its main weakness is the definition of success. The replay test in [`tests/test_lifecycle.py:135-199`](../../../tests/test_lifecycle.py) restores a completed archive as pending and replays identical content. It does not interrupt a real first write or retry an identifier with different content. The diagnostic test replaces a project file with a directory to induce a controlled error; this is useful exception testing, not abrupt process-death coverage. Runtime switching changes a profile label while reading the same checkpoint. Documentation tests check phrases and ordering, not whether a novice can complete setup.

### The live verifier proves state, not the claimed execution history

[`scripts/live_runtime_rehearsal.py:339-456`](../../../scripts/live_runtime_rehearsal.py) independently checks useful end-state facts. However, `startup_ready: true` is supplied in an agent-written evidence file. There is no controller-owned runtime identity or startup receipt. Matching checkpoint summaries and Git HEAD do not prove the commands happened in the prescribed order. An archive need only exist, and the requested reusable lesson is not checked by this verifier. The synthetic completion helper in [`tests/test_live_runtime_rehearsal.py:49-155`](../../../tests/test_live_runtime_rehearsal.py) can create accepted evidence without a model session and without calling startup.

Consequently, the statement in [`docs/LIVE_RUNTIME_REHEARSAL.md`](../../LIVE_RUNTIME_REHEARSAL.md) that a passing rehearsal proves the selected real runtime followed the tested startup path is too strong unless an observer separately establishes execution provenance. Preserve the end-state verifier, but label its result accurately. Add controller-owned operation receipts, runtime/harness versions, and event ordering if the release gate is intended to certify a live execution path. Ordinary human observation is acceptable for an explicitly human-attested smoke test; it must not be confused with machine-attested evidence.

### Missing failure coverage

The immediate regression set should cover F1-F11 plus duplicate JSON keys, long/colliding IDs, malformed recovered envelopes, unknown persisted versions, foreign checkpoints, non-string checkpoint lists, dirty/untracked artifacts, wrong-project clones sharing ancestry, partial Git operations, and mutable bridge configuration.

Crash tests should terminate the writer before and after every persistence boundary, including the final reply. Restart in a fresh process and compare complete logical state to a reference model. Inject short writes, ENOSPC, permission failures, rename/fsync failures, corrupted pointers, partial archives, and interrupted migrations. Verify that every accepted input item is either committed, recoverably pending, or explicitly rejected. Tests that only assert a `VERIFIED` string cannot establish this property.

Use independent reader/writer processes for concurrency tests. Exercise two wrap-ups, checkpoint during wrap-up, snapshot during pending state, and external-source replacement during interruption. Readers must observe one committed revision or a clearly reported recovery state, never an unmarked mixed revision.

### Portability and isolation evidence

CI currently runs on `ubuntu-latest` in both workflows. That is useful Linux evidence, not Windows/macOS certification. The live rehearsal creates a new directory but does not start an OS sandbox, restrict mounts, remove ambient credentials, or constrain network access. Calling the directory disposable limits the value of its intended contents; it does not limit what an agent process can access.

The optional semantic adapter is appropriately separate from durable state. Its configured wing is optional; search and wake-up can therefore return all provider-visible context. Provider output is passed through as text without canonical record IDs, revision freshness, or a check against current fact status. See [`scripts/semantic_memory.py:117-132, 183-204`](../../../scripts/semantic_memory.py). This needs scoped retrieval before using one installation for unrelated clients or trust domains. It does not establish that any live provider leaked information in this review.

## Direct answers to the architecture questions

### 1. Would I choose this architecture from scratch?

I would choose its ownership and storage boundaries, but not its current dependence on a model coordinating separate scripts correctly. The starting point should be a small local controller with one authoritative write interface and explicit session/project identity. Existing scripts can become thin command interfaces to that implementation; a daemon is not initially necessary.

The controller should own request validation, authorization, concurrency, operation IDs, state revisions, crash recovery, and receipts. The model supplies proposed facts, task transitions, and checkpoint descriptions. It does not decide which files to edit or whether its own output proves persistence.

Keep readable files. Store canonical structured operations or records with a committed revision, and produce Markdown views for inspection. Do not introduce a distributed event platform. A single local writer and an explicit commit point are enough to address the immediate failures. This change is motivated by F1-F5 and F11, not by a preference for a particular database or framework.

### 2. What should not be disturbed?

- User ownership and physical separation of framework, private Brain, and project work.
- Local durable state that works without a network account, Git, or semantic service.
- A unique workspace ID rather than an absolute path as workspace identity.
- Explicit unknown-runtime behavior and refusal to infer permission from a vendor name.
- Pending-operation preservation and useful recovery diagnostics.
- Atomic replacement and read-back verification as building blocks, while tightening their scope.
- Exact reviewed third-party references, quarantine, source provenance, separate activation, and candid scanner limitations.
- Preserving unrelated instruction content and refusing malformed bridge markers.
- Optional Git with a durable-path allowlist and no automatic remote push.
- CLI tests using real temporary workspaces and Git repositories; separate live-runtime and human usability gates.

These choices reduce lock-in and make the state inspectable. Fix the enforcement gaps beneath them rather than replacing the whole project.

### 3. What assumptions are weakest?

The weakest assumption is that reading an instruction bridge reliably causes future actions. A small or distracted model can skip the bridge, forget a checkpoint, invent a success marker, choose the wrong workspace, or omit an entire information category while producing syntactically valid JSON.

Other weak assumptions are that a session ID is unique and retained, a slug identifies a project, timestamp order equals commit order, a directory is private because it is outside the framework, and a Git branch plus ancestor commit identifies the intended working state. F1-F11 show why these assumptions fail independently of model intelligence.

The checklist records a local runtime that reported success without persisting the required milestone. That is repository-recorded evidence, not a session independently observed in this review. Adding stronger wording may help that model, but cannot make persistence obligatory.

### 4. Is too much responsibility assigned to the model?

Yes. The model currently selects mode and capabilities, reconstructs commands and paths, decides when work merits a checkpoint, classifies state, constructs the bundle, interprets marker text, and initiates recovery. It also has ordinary file access that can bypass those scripts.

Move mechanical decisions into the controller: binding the Brain/project, schema discovery, capability checks, revision checks, operation identity, routing, replay, verification, and evidence capture. Generate compact task-specific instructions from the same operation definitions used by validators.

Some judgment must remain with the model or person: whether a statement is useful, whether a lesson generalizes, and whether an open-ended task is actually correct. Record those as claims with provenance. The controller can prove that a claim was preserved and that a named test ran; it cannot prove every claim is true or preserve thoughts that were never submitted.

### 5. Which invariants should always hold?

| Invariant | Current gap | Mechanical enforcement |
| --- | --- | --- |
| Every accepted item is preserved exactly or explicitly rejected | Marker-only checks and recovery defaults | Canonical payload digest, item IDs, exact read-back |
| One operation ID binds to one payload forever | Reused IDs overwrite records | Immutable operation registry; conflicting retry rejected |
| A write targets one registered Brain and project | Slugs, caller paths, weak repository identity | Stable IDs and scoped session binding |
| Every mutation stays inside permitted storage | Symlinked child directories pass | Contained no-follow writes and OS access controls |
| A committed revision has one predecessor | No writer serialization | Lock plus expected-revision comparison |
| Readers see committed state or an explicit recovery condition | Multi-file writes, ignored pointer | Committed manifest/revision and consistent reads |
| Resume cannot silently discard newer state | Corrupt checkpoints skipped | Gap detection, recovery report, revision order |
| Read-only mode cannot mutate through supported operations | Startup policy is advisory | Authority checked at every mutator |
| Checkpoint proof states what was actually saved | Artifact state not captured | Artifact manifest or explicit unsaved-work warning |
| Unrelated user files and Git configuration stay untouched | Parent-repository adoption | Root identity checks and bounded mutation set |
| Optional integrations cannot override authority or block core recovery | Intent is mostly sound | Scoped adapters, timeouts, non-authoritative output |
| Unsupported formats are never silently rewritten | Partial hand-written validation | Versioned schemas and refusal before mutation |
| Private content never enters a public export implicitly | Ignore-text checks and limited scan | Export allowlist, index checks, human privacy review |
| Success names its evidence and durability scope | Generic `VERIFIED` labels | Structured receipt: revision, hashes, validation, local/replicated scope |

No code can enforce the last privacy invariant against an agent granted arbitrary host reads and arbitrary network writes. The permission model must make that restriction real; otherwise label it a policy promise rather than an enforced invariant.

### 6. Is the lifecycle correct?

Its concepts are right, but verification belongs at every transition, and recovery must precede readiness. I recommend:

```text
open Brain/project -> inspect versions and authority -> recover pending operation
  -> acquire consistent context revision -> ready
  -> work -> verify artifacts -> persist checkpoint + receipt -> continue
  -> propose wrap-up -> validate/commit -> verify projections -> optional backup
  -> close session
```

Resume is startup's recovery branch, not a second discretionary ritual. Wrap-up should be a final batch of ordinary typed operations, not a separate writer with looser validation. Verification is a condition for a transition, not a final ceremony.

Quick mode should reuse context only when its revision matches current state. Replace the unprovable `--context-loaded` boolean with a revision token; refresh the changed portion when it differs. Keep offline work possible when local state is authoritative. Reserve degraded/read-only status for uncertainty about authority or consistency, not merely loss of an optional network service.

Add an explicit interrupted/blocked session state, safe cancellation, and backup status. A cancellation must preserve committed work and explain what remains pending.

### 7. Can state be lost while reporting success?

Yes: F1-F3 reproduce false wrap-up verification, and F5 reproduces stale resume verification. In F1-F3, some missing routed information remains in an archive, so it may be manually salvageable. It is still absent from the normal authoritative view while Aham reports success. Reusing an ID can also replace the historical archive itself.

The schema fix at the reviewed commit helps new requests, but acceptance and persistence are different obligations. Verify all accepted fields and destinations. Reject duplicate JSON keys before ordinary decoding silently keeps the last value. A complete receipt should enumerate accepted items and identify their committed revision; no unknown field should disappear during normalization.

Also narrow `CHECKPOINT VERIFIED`: it currently proves checkpoint payload/pointer consistency, not that every referenced artifact or uncommitted code change is recoverable.

### 8. Can state duplicate, corrupt, misroute, or contradict itself?

Yes. F4 demonstrates lost updates; F6 duplicates a retried fact; F7 mixes projects; F1 makes archive and memory disagree. A single pending filename can be raced by multiple writers. Global checkpoint selection can choose another project's latest checkpoint. Branch and ancestry checks can accept the wrong clone of the same history.

Use stable Brain/project/session/operation identities, immutable operation payloads, serial revision assignment, and explicit task/fact transitions. Keep display names and filesystem locations as changeable attributes. Do not solve multi-machine concurrency by trusting local file locks: initially permit one writer per synchronized Brain and detect divergent revisions on import. Automatic merging of prose is not a conflict-resolution policy.

### 9. Are the framework/Brain/project boundaries right?

Conceptually, yes. Strengthen them with a fourth distinction: machine-local connection and permission configuration. It maps stable IDs to local paths and stays outside shared project content and portable Brain identity.

The framework owns code, schemas, migrations, and generic adapters. The private Brain owns personal facts, private task continuity, and references to projects. Project repositories own artifacts and deliberately shareable project documentation. Do not automatically copy source trees, client secrets, or all project conversations into the Brain.

Register project identity in the Brain, with an explicit sharing scope. Reject overlapping storage roots and symlink escapes. A project-local config is a locator, not authority to read any Brain path it names. This prevents a modified project from silently redirecting a trusted assistant into another person's or another client's context.

### 10. Should there be one strict machine-readable operations contract?

Yes. The current `core/*.json` files describe policy, but most lifecycle payload shapes and semantics are implemented separately in Python and examples. Only the third-party registry has a dedicated JSON Schema file in this snapshot.

Define versioned request and response schemas, generate command help and small runtime instructions from them, and use the same validation for initial requests, persisted records, and recovery. A proposed request envelope would carry:

```json
{
  "protocol_version": 1,
  "operation": "checkpoint",
  "operation_id": "controller-issued-id",
  "workspace_id": "registered-workspace-id",
  "project_id": "registered-project-id",
  "session_id": "controller-issued-session-id",
  "expected_revision": 42,
  "payload": {}
}
```

This is a design sketch, not a supported current command. A receipt should return status, resulting revision, normalized payload digest, item counts/IDs, verification scope, warnings, and recovery action. The command interface and any future tool protocol should call the same writer. Do not create independent implementations for shell, MCP, and individual vendors.

### 11. How should model mistakes be handled?

Use a permissive input boundary followed by a strict canonical core. Accept a small documented alias set, trim appropriate whitespace, and return explicit normalization notices. Reject alias/canonical conflicts, duplicate keys, unknown operations, wrong types, unsafe paths, conflicting IDs, and stale revisions before mutation.

Do not guess project identity, coerce arbitrary objects into strings, or invent a missing checkpoint summary. Preserve a rejected request in a scoped, bounded diagnostic location when appropriate, and return an exact field-level error plus the expected shape. Permit a bounded repair attempt. Persisted canonical records get strict validation; they should not be repeatedly reinterpreted using a growing collection of heuristics.

The existing alias handling is a reasonable starting point. Its weakness is not accepting aliases; it is lacking one canonical validation path for recovery and full preservation checks.

### 12. Do runtime adapters actually make Aham model-neutral?

They make the storage format and intended lifecycle largely model-neutral. They do not yet make execution behavior portable or enforced.

| Runtime/harness path | Evidence in the reviewed tree | Remaining gap |
| --- | --- | --- |
| Claude | `CLAUDE.md` import bridge; framework tests | Checklist's live gate remains open |
| Gemini | `GEMINI.md` import bridge; recorded live pass | Version/configuration scope and controller evidence |
| Codex | `AGENTS.md` directive; recorded live pass | Directive compliance and permission binding |
| Local models | Manual bridge; recorded unsuccessful live attempt | Context budget, tool reliability, forced persistence |
| OpenCode | No named executable adapter or conformance result | Test harness separately from the model it hosts |
| DeepSeek Harness | No named executable adapter or conformance result | Establish its actual tool/permission interface |
| Future unknown agents | Neutral profile and manual instructions | Safe read-only fallback; mediated writes need conformance |

These are repository findings, not claims about current upstream feature support. A model name, a hosting endpoint, and a harness are separate axes. DeepSeek running through one harness is not evidence for another harness. Shell-less runtimes need a connector to the same controller, or a clearly limited read/export mode. Manual file editing cannot be presented as equivalent to transactional persistence.

### 13. Would a stronger harness help local-model reliability?

Substantially, yes. Before work, the harness should select and verify the Brain/project, recover pending state, grant scoped capabilities, and supply a compact context packet at a known revision. Give the model only the operation definitions needed for its current task.

During work, capture actual tool outcomes outside model prose, enforce write scopes and budgets, and preserve submitted work at bounded intervals. Trigger checkpoints on controller-visible milestones or explicit accepted task transitions. A timer can trigger a progress save, but must not label unfinished work completed. Failed validation should produce a small actionable response and bounded retries.

After work, the harness checks artifacts, commits state through the writer, verifies the receipt, and runs an independent recovery read. Termination and model replacement become lifecycle events the controller handles. This reduces the amount of sequencing a small model must remember; it does not repair bad reasoning or fabricate omitted requirements.

### 14. Is the isolation strategy sufficient?

No. New temporary directories and separate Git branches protect organization, not host access. The rehearsal preparer does not construct a sandbox. A process running as the user can still access the real Brain, framework, credentials, or unrelated projects if its harness permits it.

Use a disposable OS-enforced environment for agent testing: a read-only framework image, writable synthetic project and Brain, a separate trusted verifier, and no real home directory, SSH agent, container socket, or personal configuration mounted. Permit only the network access needed for the selected model, using narrowly scoped disposable credentials where required. Test attempted access to a harmless sentinel outside the allowed mounts; it must be denied mechanically.

For normal use, the agent edits the selected project while a separate writer owns canonical Brain mutation. Reuse native harness isolation where it meets the contract; document unsupported platforms instead of offering an unrestricted fallback under the same safety label. A container alone is insufficient if it mounts privileged sockets or the user's home.

### 15. How good is the testing strategy?

It is a credible foundation with important missing adversarial cases. The passing suite verifies many intended paths, but its replay, switching, and documentation tests are narrower than the product promise. The evidence assessment above identifies the precise gaps.

Prioritize conservation properties: all accepted data survives; conflicting retries never mutate; concurrent writers cannot lose either accepted operation; restart selects the committed project revision; projection rebuild gives the same logical state; rejected input changes nothing. Test these through the public interface and a separate state reader, not only internal helpers.

Add actual process termination, storage-fault injection, schema upgrade/downgrade fixtures, Git worktrees and nested repositories, Windows/macOS path behavior, and unauthorized-write attempts. Keep synthetic tests for deterministic mechanics. Do not use them as substitutes for instruction-following, task quality, or human comprehension.

### 16. What needs real-agent testing?

Test what scripts cannot simulate: instruction discovery, context limits, real tool invocation, permission prompts, error repair, milestone judgment, and model replacement without the previous conversation. Use synthetic data and independent controller evidence.

Start with this small matrix, sequentially and under explicit per-run cost/time limits:

| Lane | Purpose |
| --- | --- |
| Strong hosted model in Claude's harness | Native instruction loading and lifecycle adherence |
| Strong hosted model in Codex's harness | Same task and state contract under different tools |
| Strong hosted model in Gemini's harness | Third native path and permission behavior |
| Weaker local model in its usual harness | Tight context, imperfect tool use, recovery from a rejected request |
| The same local model in OpenCode | Isolate harness effects from model effects |
| A selected model in DeepSeek Harness | Establish that harness's conformance, not inferred compatibility |

Record exact model, quantization/context settings where relevant, harness version, OS, adapter version, permission mode, prompts, and controller receipts. An unavailable lane remains untested; do not silently substitute another profile name.

Use one short task that produces a fact, a changed fact, an unfinished task, an artifact, and a checkpoint. Then run selected transitions: hosted-to-local, local-to-hosted, and harness-to-harness with no chat history. Inject termination immediately after an accepted write and restart in another runtime. Add an intentionally bad request and a permission-denied request. Unknown-runtime read-only fallback can mostly be tested without paying for another model.

Do not run the full Cartesian product. Run each advertised harness once initially, repeat the weakest path to expose variability, and rerun only affected lanes after changes. Report observed failures and human interventions alongside successes. A single successful run is a smoke test, not a reliability rate.

### 17. What is overengineered?

There is more machinery for optional integrations, release ceremony, and instruction wording than for enforcing a single state transition. The problem is allocation of complexity, not the existence of those features.

Workspace validation is duplicated across `state_io`, the standalone verifier, doctor, and rehearsal code. Git execution and JSON validation also have multiple implementations with different protections. Policy JSON, Python constants, prose, and templates repeat assumptions without one generated contract. This invites fixes that protect one path but leave another exposed, as the recovery schema gap demonstrates.

Keep existing provenance and attribution work, but defer expanding secret-based authorship commitments, skill installation features, or vendor-specific prompting until state integrity is established. Such features do not repair continuity. Similarly, Quick and Regular need not remain separate user-facing concepts if the controller can cheaply compare revisions and refresh only what changed.

Do not replace these scripts with a plugin microservice framework. Consolidate shared invariants into a deep module with a small interface, then retain simple commands for people and adapters.

### 18. What is underengineered?

Operation identity, writer coordination, project identity, schema evolution, content-level verification, and recovery ordering are the highest-risk omissions. They look like bookkeeping until two legitimate actions overlap or a retry follows a crash.

Task and fact lifecycle is also missing. Wrap-up appends unfinished-work text but provides no stable task identity or operation to complete, supersede, or cancel it. Appending another statement to Markdown leaves resolution to future models. That is an accumulating reliability cost.

Context assembly deserves more attention: startup currently reports state metadata but does not deliver a compact, project-scoped packet of current facts, open tasks, recent decisions, and evidence. A low-context model should not need to browse the entire Brain to discover what matters. A receipt and a bounded context packet should be first-class controller outputs.

### 19. What breaks with many users?

Filesystem and Git assumptions fail first: paths with spaces or non-ASCII names, case-insensitive collisions, symlink/junction behavior, read-only installs, different interpreter names, inherited Git settings, nested repositories, detached heads, worktrees, and unavailable commit identity. Native Windows and macOS need explicit test lanes; Linux-only CI is not portability evidence.

Multiple projects expose the global latest-checkpoint design. Multiple machines expose conflicting writers and machine-local bridge paths. Multiple people expose ownership, access, and namespace questions that a random workspace ID does not answer. Separate personal Brains from any deliberately shared team workspace; do not silently make a user's personal memory a team service.

Publish a supported Python/platform range and verify it during setup. Register stable workspace/project IDs with machine-local locators. Treat an enclosing Git repository as a setup warning or rejection, not a usable transport. Initially support one authoritative writer and explicit export/import for machine moves. Team collaboration is a later product with a separate permission contract.

### 20. What breaks after a year?

Memory and task files accumulate stale or duplicate statements. History and checkpoint directories grow without an index or retention plan. Resume currently scans and parses every checkpoint, and appending Markdown rewrites the whole destination. Timestamp ties, clock changes, obsolete project names, and old pending formats become routine rather than unusual.

External sources can remain pinned to obsolete versions while their working trees drift. Local bridge paths can outlive moved projects or framework checkouts. Git may preserve secrets that were later removed from current files. Semantic retrieval can keep returning invalidated facts unless the index tracks canonical revisions.

Maintain a rebuildable index over authoritative records, per-project heads, bounded context views, and explicit retention settings. Archive old completed activity only after proving it is not required for current recovery. Keep the original record when summarizing, with source IDs and a reproducible link to the summary. Test a synthetic year of operations for startup latency, disk growth, and correctness; do not use an LLM summary as the sole surviving backup.

### 21. How should memory age and change?

The current append-only prose is insufficient for changing facts. A new statement can contradict an old one without telling the next model which is current.

Give each fact a stable ID, scope, source, recorded time, optional real-world validity interval, and status such as current, superseded, disputed, or retracted. A replacement explicitly references the old fact. Preserve historical truth: a person moving cities does not make the old city false for the earlier period. Separate the time the fact applied from the time Aham learned it.

Use the same model for lessons: record applicability, supporting evidence, and a review trigger. A workaround for an old tool version should not become timeless law. Volatile facts can become due for revalidation; age alone should not silently delete or contradict them. If sources disagree, preserve the conflict and surface it rather than letting the last appended sentence win.

The writer can enforce valid transitions and references. Human or model judgment is still needed to propose a justified replacement. Retrieval should default to current facts in the selected scope and offer historical views explicitly.

### 22. Should files remain the main storage model?

Yes for the present scale, with a stricter structure and one writer. Markdown remains useful for people; canonical structured records should supply identity, revision, and lifecycle semantics. Avoid two independently editable sources of truth. If people edit a generated Markdown view, import the edit as an explicit proposed change or report a conflict before regeneration.

A database becomes justified when measured startup/recovery performance misses the product budget, indexed queries are necessary for routine operation, or file-based transactional machinery becomes more complex and less testable than a proven embedded store. Thousands of records alone are not a compelling reason. Repeated multi-record consistency failures or a need for reliable concurrent local access may justify SQLite sooner than raw data volume does.

If SQLite is chosen, keep versioned export/import, readable inspection, backup verification, and backend-independent operation semantics. Do not place a shared SQLite file on arbitrary network storage and call that multi-machine support. A network database is justified only by an explicit multi-user/service requirement, not by the wish to look scalable.

### 23. Where should semantic memory sit?

Keep it optional and secondary. It should be a rebuildable retrieval index of authorized canonical records, never the only copy of a decision or task. The current separation in `core/memory.json` and `core/semantic_memory.json` is sound.

Each result should identify its canonical source, Brain/project scope, indexed revision, and current/superseded status. Recheck important retrieved facts against current records before acting. Missing or stale indexing should reduce convenience, not block recovery. Index only committed data and propagate retractions or supersessions.

Require a selected namespace for private/client work, with an explicit broader search action when justified. Treat retrieved text as evidence-bearing data, not instructions to the agent. The current passthrough output and optional all-wing scope need stronger handling before one provider instance serves unrelated projects or users.

### 24. How can recovery become boring?

Define one commit point and a recovery algorithm that never needs to interpret prose. A minimal file-backed design could work as follows:

1. Acquire the writer lock; validate workspace/project identity, permissions, schema, operation ID, and expected revision.
2. Persist the canonical proposed operation and its payload digest in an immutable prepared record. Synchronize the required storage metadata under the supported filesystem policy.
3. Construct the next revision and all references needed to read it. Atomically publish a committed manifest that names that revision and its content hashes. This is the logical commit point.
4. Generate Markdown views and indexes from committed records. Stamp them with their source revision; readers either use that revision consistently or receive an explicit rebuilding state.
5. Verify accepted content and return a durable receipt. An exact retry returns the same receipt rather than generating another operation.

On restart, a prepared record absent from the committed manifest is incomplete and can be resumed or explicitly abandoned. A committed operation with incomplete projections is rebuilt. A missing reply after commit is resolved through its operation ID. Hash or revision disagreement is an integrity error, not permission for the model to pick its favorite file.

Test every interruption point in a new process. Use supported OS synchronization primitives and document weaker storage environments. A local lock is not a distributed lock, and atomic rename alone is not a power-loss proof.

Project Git and Brain state are separate durability domains. First preserve or identify the exact artifact revision, then record its reference in the Brain. If interruption leaves a project commit without a Brain receipt, reconciliation can safely discover it. Never claim both repositories were atomically committed. External actions such as publishing or sending messages need their own intent/result records and idempotency strategy; blindly replaying them is unsafe.

### 25. Which security and privacy risks are overlooked?

The concrete containment and privacy issues are F8-F10. Several additional trust assumptions need explicit treatment:

- **A local path is not an authorization grant.** Project-writable `.aham/runtime.json` points to framework code and private data. A changed project can redirect those paths. Validate connection identity against controller-owned registration before following it. In bridge removal, `instruction_file` is read from config and joined to the project without an allowed-filename/containment check; a crafted config can target managed content outside the project. This is a static finding in [`scripts/runtime_bridge.py:345-375`](../../../scripts/runtime_bridge.py), not an executed deletion probe.
- **Private directories need private permissions.** Setup uses normal directory creation and template copying, so initial access depends on the process umask and platform defaults. Define owner-only permissions or appropriate ACLs and check them. A separate folder is not necessarily inaccessible to other local users.
- **Git configuration executes code in more places than hooks.** Fetch/checkout and staging can encounter configured helpers, URL rewrites, filters, or executables. Treat the Git environment as trusted executable configuration and isolate it for disposable runs. Set subprocess timeouts and output/resource limits. Avoid transferring user credentials into the test environment.
- **Supply-chain review is not execution containment.** Exact commits and a structural scanner are worthwhile, but instruction injection is not ruled out by `PASS`. Read-only installation trees, scoped activation, and restricted tools matter more than expanding a keyword blacklist.
- **A current-tree privacy scan is not a publication audit.** The foundation scanner checks selected text suffixes in the working tree. It does not establish that Git history, other refs, binary artifacts, logs, release attachments, or ignored files selected by another publisher are clean. Review exactly what will be published, including history when publishing the existing repository.
- **Semantic output can cross trust domains.** Require namespace scope and revalidate source authority. Retrieved instructions or malicious project text must not gain authority over lifecycle rules.
- **Backups and diagnostic bundles duplicate private data.** Provide redaction, retention, export preview, and encryption options appropriate to the deployment. A hash is neither encryption nor permission enforcement. Default diagnostics should not upload full Brain content or model transcripts.

The threat model should distinguish accidental model mistakes, malicious project content, compromised third-party code, another local user, and a fully compromised host account. Aham can materially reduce the first four with scoped processes and trusted mediation; it cannot protect data from an attacker with unrestricted control of the account holding that data.

### 26. What observability is missing?

Pending `progress` and completed archives are a good start, but progress overwrites the previous stage and successful archives can be overwritten by reused IDs. There is no reliable chain connecting the original request, normalized accepted data, authorization decision, artifact check, and resulting revision.

Record a compact controller-owned operation journal: operation/session/project IDs, framework/protocol versions, prior/resulting revision, request and normalized-payload digests, normalization notices, stage transitions, error codes, validation results, and receipt identity. Preserve monotonic event order in addition to wall time. Record the harness's actual process/tool outcome separately from the model's claim.

A useful six-month diagnostic should answer: what was requested, what was accepted, what changed, what was rejected, which state was read, and why success or failure was reported. Support inspection by operation ID and a redacted export. Do not log secrets or full conversations by default. An untrusted model writing its own audit file is not independent observability; the controller must own the record.

### 27. Is a formal compatibility contract needed?

Yes. Individual JSON `version` fields are present, but there is no overall framework/protocol/workspace/adapter compatibility policy or migration runner. An older runtime can otherwise load newer state partially and rewrite it under old assumptions.

Declare the writer's supported read/write schema ranges, operation protocol version, required features, and framework build identity. Negotiate these before mutation. Unknown newer formats should be read-only or refused, never silently downgraded. Generated bridges should declare the protocol they expect; local framework upgrades must not invisibly change the rules mid-session.

Migrations should preflight the complete Brain, take a verified backup, acquire exclusive authority, transform a separate generation, validate references and conservation of accepted records, then atomically activate the new generation. Journal the migration so restart resumes predictably. Retain the previous generation until recovery is demonstrated. Rollback after new-format writes requires preserving/exporting those writes, not simply swapping an old directory back.

Keep stable identity independent of schema version. Currently `workspace_fingerprint` includes version and framework metadata ([`scripts/state_io.py:90-99`](../../../scripts/state_io.py)); an eventual format migration must account for historical checkpoints rather than making them appear to belong to another Brain. Distinguish restoring the same Brain from deliberately forking a new one.

### 28. How should onboarding work for a nontechnical person?

Keep the one-sentence entry point and plain-language explanations. Replace the long model-managed setup sequence with a deterministic setup command or small local wizard behind it. The assistant should explain choices, not improvise installation mechanics.

Ask only for a Brain location and the project to connect. Offer a private default location, validate it against enclosing repositories and permissions, create stable identities, and run a save/reopen test. Show a short result such as: "Your work is saved locally. Backup is not configured. This project is connected."

Provide named Brain/project selection so ordinary use does not require copying paths. Make recovery a single supported action with a preview when choices are needed. Add optional Git, semantic search, and skills later, one at a time. Do not confuse successful template creation with a tested ongoing continuity workflow. A novice walkthrough remains necessary: phrase-presence tests cannot measure comprehension.

### 29. What is the smallest reliable core?

Five pieces:

1. Stable Brain/project identities and a private location registry.
2. One versioned operation contract and strict validator.
3. One authorized writer with concurrency control, immutable operation identity, a commit point, and verified receipts.
4. One startup/recovery/context reader using committed revisions and artifact references.
5. Readable export plus verified backup/restore, with one thin runtime adapter to exercise the contract.

Basic memory, task, lesson, and checkpoint records belong inside this core. Git transport, semantic retrieval, skill installation, native hooks, dashboards, and additional runtime adapters remain optional. The core should prove continuity when all of those extras are absent.

The core promise should also be bounded: Aham preserves accepted durable state and recorded artifacts. It cannot recover unsubmitted model thoughts or arbitrary unsaved external work. Express the checkpoint interval and any remaining unsaved work clearly.

### 30. What should deliberately not be built?

Do not build a universal agent orchestrator, a new model-serving stack, a broad skill marketplace, automatic provider-account management, or an autonomous memory authority that rewrites facts without provenance. These expand the trust surface while doing little for continuity.

Avoid automatic cross-machine conflict resolution, speculative distributed consensus, full transcript retention by default, silent public/private synchronization, and custom security claims based on hidden prompts or success phrases. Do not attempt every harness integration before the common contract is reliable. Avoid a GUI that hides unverified state behind a green indicator.

Keep authorship/provenance features separate from data-integrity guarantees. Possession of a provenance secret is not evidence that a model followed the lifecycle or that a user's Brain is recoverable. Existing functionality can remain; expanding it is a lower priority than eliminating false success.

### 31. What questions are still missing?

- **What exactly is the recovery promise?** Define the maximum acceptable unsaved work and recovery time. Does "saved" mean local, backed up elsewhere, or independently restored?
- **Who owns a write during interruption?** If an old process wakes after a new session takes over, can it still commit? Authority needs expiry/revocation or fencing where takeover is supported.
- **How are human edits reconciled?** People will edit Markdown. Decide whether those edits become new canonical operations, proposed imports, or conflicts; never silently erase them by regenerating views.
- **What does deletion mean?** Retraction from current memory, deletion from backups, removal from Git history, and a request to stop sending information to hosted models are different operations. Define retention and export behavior before accumulating sensitive data.
- **What proves a backup is usable?** Disk-local Git history will not survive loss of that disk. Test restoration into a clean location and record the restored revision.
- **What happens outside Git?** Documents, notebooks, binary artifacts, local datasets, and remote side effects need preservation/reference policies. A commit hash cannot cover them all.
- **Can a framework update alter an active session?** Pin operation semantics for the session; migrate between sessions or through explicit negotiated transitions.
- **Can older but valid context cause a harmful action?** Versioned facts and task preconditions matter even when every byte was stored correctly. Revalidate material assumptions before external effects.
- **What are the resource budgets?** Limit checkpoint growth, request sizes, recursion, subprocess output, tool retries, and model cost. Reliability work should include predictable spending and sequential test execution.
- **Can users leave?** Prove a documented export remains readable without Aham, its optional services, or the original vendor. User ownership needs an exit path.

These questions need explicit product decisions. No implementation can promise "never lose continuity" without defining what is recorded, when it becomes durable, and what failures are covered.

### 32. Prioritized architecture plan

#### Must fix before broader testing

Continue narrowly scoped synthetic defect tests now, but do not expand success claims or use valuable real Brain state until these gates pass.

| Priority | Bounded change | Acceptance gate |
| --- | --- | --- |
| M1 | Strict canonical request/pending/receipt schemas; immutable operation ID and digest; exact content verification | F1-F3 and F6 regressions pass; unknown/duplicate fields and conflicting retries cause no mutation; exact retries return the same receipt |
| M2 | Single writer, expected revisions, committed state boundary, recovery journal | Independent concurrent processes preserve all accepted operations or return explicit conflicts; kill/restart at each write boundary conserves state |
| M3 | Stable project IDs, per-project checkpoint heads, monotonic ordering, explicit degraded recovery | F5/F7 regressions pass; corrupt latest state is reported; wrong project/clone and unpreserved artifacts cannot be called fully verified |
| M4 | Filesystem/Git containment and effective private-config checks | F8-F10 regressions pass; symlinks, nested repositories, tracked private config, and config path traversal are refused before mutation |
| M5 | Controller-enforced session authority and an actual disposable sandbox | F11 is denied through the write interface; sentinel outside allowed storage cannot be read/written by the test agent; real secrets/framework are not writable mounts |
| M6 | Correct success semantics and evidence-based release claims | Receipts identify accepted revision and verification scope; artifact-only rehearsal results are labeled accurately; docs no longer equate script/profile tests with live runtime behavior |

Implement these as small reviewable changes, preserving the existing command interfaces where feasible. Start with failing regressions for the demonstrated defects. Extract the shared writer/validator incrementally; do not attempt a single large rewrite plus new features. After each stage, save a checkpoint, commit, and demonstrate fresh-process recovery.

#### Should fix before public release

| Priority | Change | Acceptance gate |
| --- | --- | --- |
| R1 | Compatibility policy and migration runner | Old/new/unsupported fixtures preserve data or refuse writes; interrupted migration and rollback are exercised |
| R2 | Fact supersession and task transitions with IDs/provenance | A changed fact returns as current without losing history; completed tasks stop appearing open; conflicting sources remain explicit |
| R3 | Compact context assembly and runtime conformance tiers | Selected runtime matrix passes within documented context/cost limits; model switches recover correct project state without chat history |
| R4 | Verified backup/export/restore | Restore to a clean machine/location without semantic services; compare record/artifact manifests; distinguish local save from replicated backup |
| R5 | Platform and Git-environment hardening | Supported OS/Python matrix, spaces/Unicode, worktrees, permissions, inherited config, timeouts, and source-activation crash tests pass |
| R6 | Scope semantic retrieval and external activation | Cross-project/client leakage tests pass; stale/retracted facts are filtered or labeled; activated content matches reviewed/scanned identity |
| R7 | Nontechnical setup and trustworthy diagnostics | A new user completes setup, a model switch, and interrupted recovery; reports name concrete next actions without false readiness |
| R8 | Publication audit of the actual release and history | Automated checks plus human review cover all published artifacts/refs; runtime/test claims match retained evidence; maintainer authorizes release |

A formal migration and restore path is a release requirement because the first public user's data will outlive the first public framework version. It should not be postponed until incompatible state already exists.

#### Useful later

- Additional harness adapters after they pass the same conformance contract.
- SQLite or another backend if benchmarks or transactional complexity justify it; retain portable export.
- A read-only history/recovery viewer and convenient local setup UI.
- Incremental semantic indexing, retention tooling, and reversible archival with measured context benefits.
- Multi-machine replication with explicit conflict handling and a deliberately chosen writer/authority model.
- Team workspaces only after a separate multi-user access and sharing design.

#### Do not change

- User-owned, inspectable state and a usable export path.
- Public framework/private Brain/project separation, strengthened by enforcement.
- Local operation without required cloud, Git host, semantic service, or skill loader.
- Vendor-neutral formats and honest unknown-runtime limitations.
- Exact third-party provenance, quarantine, attribution, and separate permission grants.
- Preservation of unrelated files and instructions; explicit review before publication.
- Independent verification and small recoverable milestones as goals, with stronger evidence beneath them.

The immediate architectural goal is modest and testable: after any accepted operation, retry, interruption, or supported model switch, a fresh reader can explain exactly what is committed, what remains pending, and what has not been preserved. That is the foundation on which broader runtime support should depend.
