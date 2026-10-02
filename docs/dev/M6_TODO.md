# M6 anti-drift todo

This file is the working todo for architecture-remediation milestone M6. The controlling requirements remain `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md`; `PROJECT_CHECKLIST.md`, README, and runtime-rehearsal documentation are inputs to reconcile, not independent sources of truth.

M6 starts from `main` commit `b26ea27aace287886721d3a37db2ea9194150453`, after M5 implementation PR #24 and its completion-record PR #25 were merged.

## Anti-drift rule

For each M6 behavior change:

1. reproduce the imprecise/missing evidence behavior with a regression test before changing it;
2. preserve M1-M5 identity, writer, recovery, containment, and authority guarantees;
3. make the smallest generic change that improves the evidence contract;
4. run Foundation verification and the complete unit suite;
5. update this TODO and the architecture checklist only after the corresponding acceptance evidence exists;
6. do not resume broad runtime/harness comparison work until M6 is complete.

## A. Structured operation receipts

- [x] Define a versioned structured receipt/evidence schema shared by checkpoint and wrap-up where practical.
- [x] Checkpoint success reports operation ID, committed revision, payload digest, accepted item/checkpoint identity, verification scope, warnings, and recovery action.
- [x] Wrap-up success reports operation ID, committed revision, payload digest, accepted item IDs/counts/destinations, checkpoint identity, verification scope, warnings, and recovery action.
- [x] Status/retry output can independently reconstruct the same committed result after process restart.
- [x] Pending/recovery output distinguishes pending state from committed state and states the exact recovery action.

Initial observation before M6 changes: checkpoint currently prints `CHECKPOINT SAVED` / `CHECKPOINT VERIFIED`, checkpoint ID, revision, file and optional Git identity, but not operation ID, payload digest, verification scope, warnings or recovery semantics. Wrap-up already prints operation ID, revision, payload digest and item count, but not the accepted item IDs/destinations, verification scope, warnings, or a structured recovery field.

A acceptance evidence: regression-first commit `1eaa21dc784980d8f9e2bf411b170913fefcb71b` kept Foundation verification green while workflow `35444665178` failed only the two new complete-receipt tests because checkpoint and wrap-up did not yet accept `--json`. Shared versioned complete receipts then passed the full workflow at commit `fbb127258264189cd4f186146c3bde1b7af9d189` (run `35445201008`). Pending/recovery regression commit `02f8dd2274ba429a4a5eb236df822d1de8f83168` again kept Foundation green while run `35445329570` failed exactly the two new pending-status tests because no committed record existed yet. Commit `2b4f4c2e80f4de515d6b9bb211fd61990286fe99` added pending structured receipts and exact recovery actions; workflow `35445513984` passed Foundation plus the full unit suite. Exact wrap-up retry reconstruction was then exercised at commit `b265234c0d1f40b2c02407d27549d83a4b25b372`; workflow `35445617774` passed the complete suite and proved the retry returns the same structured committed result rather than creating a second revision.

## B. Precise success semantics

- [x] Define distinct terms for local durable persistence, content/artifact verification, Git-history verification, replicated backup, runtime instruction compliance, and end-to-end recovery.
- [x] `CHECKPOINT VERIFIED` cannot imply uncommitted/untracked/editor state was preserved.
- [x] `WRAP UP VERIFIED` cannot imply unrelated project artifacts or external backup were preserved.
- [x] `RESUME STATE VERIFIED` always states the exact verification scope and cannot imply unsaved editor buffers or excluded working-tree state were preserved.
- [x] Degraded/recovery results state committed revision, recovered revision when applicable, continuity gap, warnings, and next recovery action.

Initial observation: `resume.py` already printed explicit verification scope on successful repository-bound and workspace-only recovery and degraded when tracked/untracked state lay outside checkpoint scope, but checkpoint/wrap-up used broad standalone success markers and degraded resume did not always state a recovery action.

B acceptance evidence: regression-first commit `3e021f63e039156f709206ae5c8b45cf48d0c4dd` kept Foundation verification green while workflow `35445738012` failed exactly four new scope tests: checkpoint and wrap-up still emitted broad standalone `VERIFIED` lines, resume still emitted a broad standalone success line, and corrupt-newest degraded recovery had no explicit recovery action. Commit `f4fdfd1a59301effd8abc0f0a2f6cd5695509c1b` replaced successful human-facing lifecycle output with qualified receipt language, explicit persistence/verification/exclusion scope, and explicit degraded recovery actions; workflow `35445942348` passed Foundation plus the complete unit suite. `docs/EVIDENCE_SEMANTICS.md` records the distinct meanings of local durability, content verification, Git-history verification, replicated backup, runtime compliance, and end-to-end recovery.

## C. One runtime/harness evidence register

- [x] Define one durable versioned register for live runtime/harness evidence.
- [x] Each entry can record exact runtime/model, harness and harness version, OS/platform, framework commit, rehearsal ID, permission mode, result, human intervention, and context/quantization when relevant.
- [x] Evidence entries distinguish framework/profile tests from real live-runtime rehearsals.
- [x] Historical evidence can be migrated or represented without inventing fields that were never recorded.
- [x] Live rehearsal verifier writes or emits register-compatible evidence only after independent verification.
- [x] One run remains a smoke test, never a reliability percentage.

C acceptance evidence: regression-first commit `5c896459ce2850aa7dd4b4341eadd16d80cb504a` kept Foundation verification green while workflow `35446209987` failed exactly the five new evidence-register tests because the validator/register did not exist. Commits `b819d55032d14b73b7c04f9bfec570cdcc4d8f74` and `19b22c3513fd3dfb2e57f530e2523f8f83c44344` added the strict versioned validator plus canonical `evidence/runtime_harness_register.json`; workflow `35446795112` passed Foundation and the complete unit suite. Historical Gemini, Codex and local observations preserve unavailable metadata as `null`, framework/profile evidence has a separate claim scope, duplicate live rehearsal identities are rejected, and reliability fields are rejected. Regression commit `b27bf19979ebc60669bfac2ae71bc68c39629cad` then made workflow `35446874204` fail only because a successfully verified rehearsal report did not yet contain register-compatible evidence. Commit `f401246172475e572017d18a6871c70ab8a9f15b` added that emission only after the independent verifier's trusted checks complete; workflow `35447024699` passed Foundation and the complete unit suite.

## D. Documentation reconciliation

- [x] Inventory runtime/test claims in README, `PROJECT_CHECKLIST.md`, live-rehearsal docs, and other release/status documents.
- [x] Mechanically reconcile or generate runtime status from the evidence register where practical.
- [x] Remove or clearly label contradictory/stale manual runtime summaries.
- [x] Documentation no longer equates framework/profile tests with live runtime behavior.
- [x] README and `PROJECT_CHECKLIST.md` agree on current runtime evidence and its scope.

D inventory covered README, `PROJECT_CHECKLIST.md`, `docs/LIVE_RUNTIME_REHEARSAL.md`, `docs/TEST_PLAN.md`, `docs/RUNTIME_PORTABILITY.md`, and the runtime-adapter documentation. Regression-first commit `c5a71daea202013758008870f1836ceeace502ab` kept Foundation green while workflow `35447121400` failed all four new reconciliation tests because the documentation had no generated register block, README still listed already-verified Gemini/Codex rehearsals as remaining, the checklist retained a manual historical summary, and the live rehearsal guide did not name the canonical register/scope. `scripts/runtime_evidence.py` now renders and checks one canonical Markdown status block, verifies Phase 6 live-runtime checkboxes against the same register, and README/checklist carry identical generated evidence. The live rehearsal, test-plan and portability docs now keep framework/profile evidence distinct from real live-runtime evidence. Workflow `35447415695` at commit `efc5d9e0b694be01467bad8f7aeb14c95606bba0` passed Foundation plus all 156 unit tests.

## Acceptance and merge gate

- [x] Regression-first tests demonstrate the current missing/imprecise receipt fields before implementation.
- [x] Receipt/status tests survive restart and independently describe the committed operation.
- [x] Success-scope tests demonstrate that checkpoint, wrap-up and resume never claim more preservation than proved.
- [x] Evidence-register tests enforce one schema/source of truth and reject malformed/contradictory entries.
- [x] Documentation reconciliation tests or generated checks detect drift.
- [x] Full Foundation verification and complete unit suite pass.
- [x] Cross-check M6 against `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` before marking M6 complete.
- [x] Record exact M6 acceptance evidence in the architecture checklist.
- [x] Open an M6 PR, inspect the complete diff, require a fresh PR-context Foundation run, and merge only if clean.

The architecture checklist cross-check at commit `9c569694166e37da7756e6546ccb04bad275e2c5` confirmed that every M6 implementation item and all three architecture acceptance gates were backed by regression-first and green workflow evidence. M6 integration then completed through PR #26 at reviewed head `f7424d8f82c47b121e534d1ded161c2b4a2f234a`; fresh pull-request-context Foundation workflow `35447945519` passed before PR #26 merged to `main` on 2026-09-19. This checkbox was reconciled afterward because the working TODO had remained stale even though the controlling architecture checklist and repository history already showed M6 complete.

Broad runtime/harness comparison work may resume only under the post-M6 gates recorded in `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` and the canonical runtime evidence process.
