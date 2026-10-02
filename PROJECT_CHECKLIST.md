# Aham Brahmasmi build checklist

This checklist is the project-level guardrail against scope drift, accidental private-data leakage, unverified claims, and premature release.

## Phase 0: foundation

- [x] Repository exists separately from all private personal projects.
- [x] Repository is private during development.
- [x] Apache License 2.0 is present.
- [x] Root project rules exist in `AGENTS.md`.
- [x] Public/private separation rules exist in `docs/PUBLIC_BOUNDARY.md`.
- [x] Third-party source policy exists in `docs/THIRD_PARTY_POLICY.md`.
- [x] Machine-readable third-party registry exists at `third_party/registry.json`.
- [x] Foundation verification script exists.
- [x] GitHub Actions runs foundation checks automatically.
- [x] Final Apache attribution policy and `NOTICE` contents are defined for the current framework.
- [x] Donation/support wording decided before public release.

## Phase 1: first-time experience

- [x] Create `START_HERE.md` for a person who does not know the technical architecture.
- [x] The only required first instruction should be equivalent to: `Read START_HERE.md and set this up for me.`
- [x] Setup detects available runtime capabilities instead of assuming a vendor or tool.
- [x] Setup explains choices in plain language before asking the user to choose.
- [x] Setup creates or connects a new user-owned private workspace without importing any existing personal workspace.
- [x] Setup verifies the resulting workspace before reporting success.
- [x] Manual setup remains documented for people who do not want assisted configuration.

Verification: automated first-run tests create a clean private workspace, verify it, reject in-repository placement, reject overwrite of non-empty state, and reject corrupt workspace identity.

## Phase 2: Brain core

- [x] Define the model-neutral core contract.
- [x] Define Quick mode.
- [x] Define Regular mode.
- [x] Define degraded/offline behavior.
- [x] Define capability detection.
- [x] Define state routing and validation.
- [x] Unknown runtimes have safe fallback behavior.
- [x] No core rule depends on Claude, Gemini, Codex, ChatGPT, or a local model specifically.

Verification: core contract tests validate mode behavior, capability-ordering, state destinations, and unknown-runtime fallback.

## Phase 3: memory

- [x] Define a durable memory interface.
- [x] Define Git-backed durable state without requiring a specific hosting provider.
- [x] Add executable MemPalace semantic-memory adapter behavior.
- [x] Brain starts and core lifecycle works when MemPalace is unavailable.
- [x] Memory backend can be replaced without rewriting the core lifecycle scripts.
- [x] Checkpoints contain enough information to resume after interruption without reconstructing completed work.

Current implementation: local user-owned workspace files remain the required durable backend. Optional Git transport can initialize local version history and create commits containing only an explicit durable-state allowlist. It does not require a remote, does not create or choose a hosting provider, does not push automatically, excludes transient and third-party source trees, and isolates transport-created commits from configured Git hooks. `core/semantic_memory.json` defines a replaceable optional semantic-memory interface. `scripts/semantic_memory.py` implements the reviewed MemPalace CLI path for verified configuration, status, search, wake-up recall and disable behavior without making MemPalace a startup requirement or authoritative durable store.

Verification: lifecycle tests create and recover checkpoints without MemPalace, accept a newer descendant commit on the same branch, and reject a branch mismatch. Git transport tests verify operation without a remote, strict durable-path staging, exclusion of third-party/transient paths, refusal when an unrelated path is pre-staged, repeat snapshots, and hook isolation. Semantic-memory tests use a controlled provider executable to verify live-command detection, provider configuration, scoped recall, wake-up recall, failure fallback, disable behavior and provider replaceability without requiring MemPalace in the core test environment.

## Phase 4: skills and external tools

- [x] S1: scanner v2 fixture corpus, waiver invalidation and reviewed-source false-positive evidence. PR #50; exact-head workflow `36873888390` passed six jobs. See `docs/S1_SCANNER_EVIDENCE.md`.
- [x] S2: portable skill index, progressive disclosure and authority-checked enable/disable. PR #52; exact corrected-head workflow `36879782673` passed six jobs. Native copies are deferred under D4.
- [x] S3: reviewed updates, rollback/crash recovery, removal and local-source lifecycle.
- [x] S4: reviewed optional recall integration, project scope, safe envelope and opt-in indexing (PR #57; corrected gate `36904820142`, 343 Linux tests and 308 per portability job; Windows refusal only). D10 includes offline keyword recall. Whole-tree provider FAIL remains blocked from source activation.

- [x] Define the third-party registry schema completely.
- [x] Every external source currently offered by the project has a verified public upstream URL.
- [x] Every external source currently offered by the project has a recorded license and license URL.
- [x] Every external source currently offered by the project records the exact reviewed Git commit.
- [x] Prefer upstream links and reproducible fetching instead of copied trees.
- [x] Define quarantine before activation for new or changed installable sources.
- [x] Add a scanner interface so a scanner can be replaced later.
- [x] Unaccepted scanner `REVIEW` or any `FAIL` prevents activation and does not damage an existing active source.
- [x] Local adaptations, if introduced, must preserve upstream attribution and record the original commit, summary and changed paths.
- [x] Users can request the reviewed default set without manually hunting for each upstream project.

Current verified public sources: MemPalace and Superpowers are registered with exact reviewed Git commits, MIT licenses, license URLs and attribution. MemPalace remains an independently installed optional semantic-memory source connected through an adapter. Superpowers is the first installer source and is fetched from its original upstream into the user's private workspace rather than copied into this repository. `THIRD_PARTY_NOTICES.md` summarizes their independent ownership and reviewed source information without pretending those projects are licensed under Aham Brahmasmi's Apache license.

Current supply chain: registry -> exact commit fetch -> quarantine -> scanner -> activation on `PASS` or valid explicit per-finding human acceptance -> installed provenance and receipt. The offline deterministic scanner checks structural, instruction and execution surfaces; it does not prove safety. FAIL and incomplete scans cannot be waived. Runtime-specific hooks and permissions remain a separate layer.

Verification: synthetic tests cover exact-commit fetching, quarantine, PASS activation, explicit acceptance, invalidation, receipts, symlink rejection and preservation after blocked replacement. Foundation checks require registry attribution in the notices. S1's historical live-upstream rehearsal blocked a FAIL scan. S3's tested context corrections produce REVIEW for the unchanged Superpowers pin; 98 REVIEW findings remain unaccepted, so activation is still blocked. S3 lifecycle and recovery gates passed in workflow `36897056292`, merged through PR #55. Earlier structural-only activation results are historical.

## Phase 5: lifecycle and recovery

- [x] Startup executable reports runtime, explicitly verified capabilities, memory status, recovery state and state freshness.
- [x] Long or multi-stage work creates milestone checkpoints through the portable runtime bridge instructions after meaningful verified milestones.
- [x] Crash/restart can recover from the last durable checkpoint.
- [x] Recovery verifies workspace identity and recorded repository state before continuing.
- [x] `wrap up` routes durable facts, project state, unfinished work, lessons, history, and a final checkpoint to their proper destinations.
- [x] Wrap-up validates the transaction and verifies persisted markers/checkpoint before reporting completion.
- [x] Checkpoint and wrap-up commands read back their durable state before emitting their verified success markers.
- [x] A failed wrap-up reports the exact remaining replay-safe step, useful step detail when available, and a recovery command while preserving the pending transaction.

Current implementation: `scripts/startup.py` produces a model-neutral ready report and refuses to infer capabilities from a runtime name. `scripts/checkpoint.py`, `scripts/resume.py`, and `scripts/wrap_up.py` provide the model-neutral lifecycle commands. `scripts/runtime_bridge.py` installs a project-local lifecycle bridge for Claude, Gemini, Codex, local and unknown profiles. The bridge instructs capable runtimes to checkpoint after meaningful completed milestones and to route `wrap up` through the replay-safe lifecycle. Private local paths live only in Git-ignored `.aham/runtime.json`; portable `.aham/runtime.md` contains no private paths. Checkpoint success is reported only after the written checkpoint and latest-pointer file are read back and matched. Wrap-up success is reported only after routed state, the final checkpoint, latest pointer and completed archive are read back and validated. The runtime bridge treats `CHECKPOINT VERIFIED` and `WRAP UP VERIFIED` as the required in-session proof markers and explicitly forbids treating generated prose as tool evidence. Wrap-up writes a pending transaction first, records progress before each replay-safe stage, uses idempotent markers [safe to replay without duplicates], creates a final checkpoint, and archives the completed transaction.

Verification: automated tests cover startup reporting, Quick-mode context confirmation, pending-wrap-up blocking, checkpoint creation and read-back verification, recovery, Git-state checks, wrap-up routing and read-back verification, pending-transaction blocking, replay after an interrupted wrap-up without duplicate state, forced mid-wrap-up failure, exact remaining-step diagnostics, successful replay after the failure condition is corrected, runtime bridge installation/removal, preservation of existing runtime instructions, local path isolation, manual local/unknown fallback and malformed/symlink refusal. The private release rehearsal also exercises setup -> checkpoint -> repository continuation -> verified resume -> wrap-up in a new isolated workspace.

## Phase 6: runtime portability

- [ ] A1: user-trusted unlisted runtimes, writer self-test, single entry point and validated chat paste mode.
- [ ] E1: retained Claude/unlisted-runtime/chat evidence and measured instruction budget.

- [ ] Claude-compatible live runtime path tested.
- [x] Gemini-compatible live runtime path tested.
- [x] Codex-compatible live runtime path tested.
- [x] At least one local/open-model live runtime path tested.
- [ ] Reduce runtime-bridge and live-rehearsal context footprint so a capable local coding runtime with roughly 32k-40k context can start and perform normal Aham work where practical.
- [x] Unknown-runtime fallback tested end to end at the framework level.
- [x] Lack of a native skill loader does not prevent basic startup and durable-state inspection.
- [x] Lack of semantic memory does not prevent the implemented core lifecycle.

Current implementation: neutral runtime profiles and portable project bridges exist for Claude, Gemini, Codex, local/open-model use, and unknown runtimes. Claude and Gemini bridges use their verified project instruction/import mechanisms; Codex uses a managed `AGENTS.md` directive without inventing an import syntax; local and unknown runtimes receive an explicit manual read instruction. Runtime names grant no capabilities. Automated framework tests verify the bridge lifecycle and that different profiles can read the same durable checkpoint from the same private workspace. The release rehearsal installs and inspects every bridge profile in isolated project folders, but this does not substitute for authenticated sessions in the actual runtime products.

A standardized live-runtime gate now exists at `scripts/live_runtime_rehearsal.py`, documented in `docs/LIVE_RUNTIME_REHEARSAL.md`. It prepares a disposable Brain and project, gives the actual runtime an exact startup/work/checkpoint/wrap-up task, and verifies the resulting task commit, workspace identity, checkpoints, routed state and completed wrap-up independently afterward. Automated tests validate the preparation and verifier mechanics. The runtime checkboxes above are also mechanically checked against the canonical evidence register.

<!-- runtime-evidence-status:start -->
Runtime evidence source of truth: `evidence/runtime_harness_register.json`.

| Runtime/profile | Current evidence | Scope |
| --- | --- | --- |
| Claude | No live rehearsal evidence recorded | Live release gate remains open |
| Gemini | Independently verified live pass: `b0297e8c74964d06` | Single-run smoke test only, not a reliability estimate |
| Codex | Independently verified live pass: `92b48a8cc3e94f8a` | Single-run smoke test only, not a reliability estimate |
| Local/open-model | Independently verified live pass: `40d65ed2680049e3`, `037378a6a24347e7`, `753043981c7d4b1d` | Single-run smoke test only, not a reliability estimate |
| Framework/profile tests | Automated framework/profile pass recorded | Framework/profile only, not live-runtime evidence |

A live pass records one independently verified rehearsal in one tested environment. It does not establish a reliability percentage or prove other runtime/model/harness configurations.
<!-- runtime-evidence-status:end -->

## Phase 7: nontechnical usability

- [ ] R7: verified prerequisites, concrete failure guidance and fresh-user walkthrough evidence after A1.

- [x] README starts with the human problem, not architecture jargon.
- [ ] A first-time user can understand the project without knowing Git terminology. Final human walkthrough still required.
- [x] Advanced or project-specific terms in the normal first-run path are explained in plain language where the user first encounters them.
- [x] Installation has a guided path and an inspect-everything path.
- [x] Common failures explain what happened and what the person should do next.
- [x] The normal assisted setup does not require the person to understand filesystem layout, Git, Python, containers, MCP, or model-specific configuration.

Current usability support: `START_HERE.md` begins with the one instruction a normal user needs and defines Brain, framework, workspace, runtime, checkpoint, wrap up, semantic memory, Git and skill before the technical assistant instructions. `scripts/doctor.py` checks required and optional setup state and gives a next action. `docs/TROUBLESHOOTING.md` explains common setup, recovery, memory, Git, external-source and runtime-bridge failures without requiring the person to diagnose the architecture first.

## Phase 8: release gate

- [x] W1: native Windows locking/concurrency, filesystem/ACL boundaries and hosted evidence, per D3 (PR #64; gate `36936673766`, Python 3.14/local NTFS; exact scope in `docs/PLATFORM_SUPPORT.md`).
- [x] R6: scoped unverified recall, safe envelopes and reviewed activation identity (PR #48, workflow `36866478419`; Windows refusal only).
- [ ] Complete S1-S4, A1, R7, applicable W1 and E1 gates in the controlling checklist.
- [ ] R8: contributor/security/release files, CI hardening and all-branch/all-PR privacy review.
  - [x] Repository materials, hardened CI and verified maintainer checklist (PR #66;
    hosted `36938429399`, 412 Linux tests plus offline rehearsal).
  - [ ] Final all-branch/all-PR privacy scan, human review, provenance and publication authorization.

Do not make the repository public until all applicable items below pass.

- [ ] Full test plan passes. Remaining live-runtime and human walkthrough gates remain.
- [ ] No personal memory, private project data, credentials, private URLs, account identifiers, hostnames, or machine-specific paths are present. Final pre-publication privacy review still required.
- [x] Every third-party dependency/source currently offered by the project has a license and attribution review.
- [x] No third-party source tree is redistributed by this repository; installable sources are fetched from their original upstream at the reviewed ref and retain their own license/attribution.
- [x] Apache 2.0 attribution approach and `NOTICE` file are finalized for the current framework.
- [x] Commercial-use/credit expectations match the actual Apache 2.0 license wording.
- [x] Authorship/provenance evidence strategy and verification tooling are defined.
- [ ] Generate the public `PROVENANCE_COMMITMENT.json` from a fresh offline secret for the final reviewed pre-release tree.
- [ ] README statements match implemented behavior. Recheck after the remaining live/human gates.
- [x] Fresh clean-checkout setup rehearsal passes in GitHub Actions.
- [x] Crash-recovery release rehearsal passes.
- [x] Runtime-switch live rehearsal release gate passes. Independently verified DSH -> fresh OpenCode recovery switch `ce20b314417d44af` recovered the exact durable revision/checkpoint without prior session continuation or a marker-bearing handoff.
- [x] Core lifecycle test passes with MemPalace unavailable.
- [x] Third-party live install/reproducibility rehearsal passes against the approved default source at its exact reviewed commit.
- [ ] A nontechnical first-time-use walkthrough has been performed from a clean environment.

Private release rehearsal run after PR #11 exercised the complete implemented framework lifecycle and live approved-upstream installation on a clean GitHub-hosted environment. It passed. This does not convert framework simulation into a claim that external runtime products were authenticated and live-tested.

Publication required explicit maintainer authorization. The maintainer authorized a public preview on 2026-10-02 (release-plan decision D2 option b); the unchecked items above remain open for 1.0.
