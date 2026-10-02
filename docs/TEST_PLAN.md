# Acceptance test plan

These tests exist to keep the project aligned with its purpose when work continues across sessions, models, or contributors.

The private GitHub Actions rehearsal exercises the parts that can be verified mechanically in a clean environment. It does not convert a simulated runtime profile into a claim that Claude, Gemini, Codex or a local model was actually authenticated and used. Human usability and final privacy review also remain human gates.

## 1. Clean-room separation test

Goal: prove the project stands on its own.

- Clone only this repository into a clean temporary environment.
- Do not provide access to any maintainer-owned private repository or personal workspace.
- Run setup and the basic startup flow.
- Fail if initialization requires unrelated files, private URLs, personal machine paths, or hidden services.
- Fail if repository text contains credentials or obvious user-specific absolute paths.

Pass condition: a stranger can initialize the framework without any private maintainer context.

Automated coverage: `scripts/release_audit.py`, `tests/verify_foundation.py`, and the private release-rehearsal workflow.

## 2. First-time nontechnical setup test

Goal: prove the user does not need to understand the architecture first.

Starting from a fresh clone, the user gives one instruction equivalent to:

`Read START_HERE.md and set this up for me.`

The runtime should:

- explain what it is doing in plain language;
- detect available capabilities rather than assume them;
- ask only for information genuinely needed from the user;
- create or connect a new private workspace;
- verify the result before claiming setup is complete.

Pass condition: setup succeeds without requiring the user to know Git internals, filesystem conventions, memory-backend terminology, or model-specific configuration.

Mechanical setup behavior is tested. Final pass still requires a clean human walkthrough by a nontechnical first-time user.

## 3. Runtime-switch test

Goal: the Brain belongs to the user, not to one model.

- Start a small test project using runtime A.
- Record project state, an unfinished task, and a durable fact.
- Close runtime A.
- Open runtime B against the same user workspace.
- Load Regular mode.

Pass condition: runtime B recovers the same durable project/task state without a model-specific handoff file being manually located by the user.

Framework-level profile switching is automated. Final release still requires live sessions for any named runtime gate that remains open. Use `scripts/live_runtime_rehearsal.py` and `docs/LIVE_RUNTIME_REHEARSAL.md` to prepare an isolated run and independently verify each actual runtime without treating its own success message as proof. Retained live results are recorded in `evidence/runtime_harness_register.json`; framework/profile tests are a separate evidence type and cannot substitute for a live-runtime rehearsal.

## 4. Quick versus Regular mode test

- Regular mode must verify or load current durable context.
- Quick mode must use already-loaded context and avoid an unnecessary full refresh.
- Both modes must retain the same core safety and state rules.

Pass condition: observable behavior differs only where the mode contract says it should.

Automated coverage: core startup and runtime portability unit tests.

## 5. Crash-recovery test

Goal: interruption should cost minutes, not the whole session.

- Begin a multi-stage task.
- Complete at least one logical milestone.
- Create a durable checkpoint.
- Terminate the active process without running wrap-up.
- Restart using the same workspace.
- Load the latest checkpoint and verify current state before continuing.

Pass condition: work resumes from the last verified milestone and does not invent steps that were never completed.

Automated coverage: lifecycle unit tests and the isolated private release rehearsal.

## 6. Wrap-up routing test

Create a synthetic session containing all of the following:

- one durable fact;
- one project-specific update;
- one unfinished task;
- one reusable lesson;
- one dated history item.

Run wrap-up.

Pass condition: each item is written to the intended destination, state validates, and unrelated state is not modified.

Automated coverage: lifecycle unit tests and the isolated private release rehearsal.

## 7. MemPalace optionality test

Run the same startup and basic work flow twice:

1. with MemPalace available;
2. with MemPalace unavailable.

Pass condition: semantic recall improves when available, but startup and core operation still work when it is absent.

Automated coverage: controlled semantic-memory adapter tests verify the provider path and failure fallback; the release rehearsal verifies that a fresh Brain works with semantic memory unconfigured. A live MemPalace connection is optional rather than a public-release dependency.

## 8. Third-party reproducibility test

For every entry in `third_party/registry.json`:

- verify the upstream URL is public and reachable;
- verify the recorded license;
- verify the reviewed source reference exists;
- retrieve the exact recorded source using the declared integration method;
- verify local adaptation metadata when applicable.

Pass condition: a new user can obtain the approved source without depending on the maintainer's machine or a private mirror.

Automated coverage: registry/unit tests plus the isolated live-upstream rehearsal's
exact-pin scan and activation boundary. A blocked scan is retained as evidence,
not accepted merely to complete an installation.

## 9. Skill quarantine and scanner test

- stage a harmless clean fixture and confirm it can pass review;
- stage a deliberately suspicious test fixture and confirm it cannot become active;
- confirm a failed candidate does not replace an already working skill;
- confirm scanner unavailability is reported rather than silently treated as a pass.
- verify corpus verdicts, escaped findings, content/rule-pack waiver invalidation,
  read-only refusal, forged-report rejection and bounded 10,000-file scanning;
- verify opt-in advisory responses and external adapters only raise concern;
- record pinned Superpowers findings without executing or automatically accepting them.

Pass condition: unreviewed or failed candidates cannot become active.

Automated coverage: external-source tests and 25 S1 regressions. Exact S1 head
`de9c1eaec9de42ee2cbfcec7337c186fbc0cc660` passed workflow `36873888390`: 273 Linux
tests, 238 per portability job, macOS two skips per job, Windows refusal boundary.

## 10. Unknown-runtime test

S2 framework acceptance is recorded separately from live runtime consumption:
13 regressions cover revisioned index creation, compatibility summary, project
preferences, receipts, read-only refusal, committed activation proof, cache tampering
and interruption, drift exclusion, context budget, optional failure/revision isolation,
CLI and POSIX aliases. Head `476222d` passed `36879782673`: 286 Linux tests and
251 per portability job (macOS two skips per job), plus Windows refusal. The bridge
rules are tested as generated text; this does not certify a new live runtime run.

Run the core without a named runtime adapter.

Pass condition: the Brain reports unavailable capabilities, stays within safe fallback behavior, and does not fabricate tool access.

Automated coverage: startup, runtime portability and runtime bridge tests.

## 11. Privacy and secret test

Scan repository content before every release for:

- private keys;
- access tokens;
- obvious secret formats;
- absolute personal home-directory paths;
- private infrastructure details;
- accidental personal memory or project data.

Pass condition: automated scan passes and a human review also finds no private material.

Automated coverage: `tests/verify_foundation.py`. The final human review remains mandatory immediately before publication.

## 12. Documentation truth test

For every major claim in README and START_HERE:

- identify the implementation or test that supports it;
- remove or clearly mark behavior that is planned but not implemented.

Pass condition: documentation never promises more than the repository can currently do.

Runtime/harness status in `docs/STATUS.md` and `PROJECT_CHECKLIST.md` is generated from `evidence/runtime_harness_register.json`. `scripts/runtime_evidence.py check-docs` verifies the generated blocks and checks the Phase 6 live-runtime checkboxes against the same register so those documents cannot silently drift apart.

This check must still be repeated after the final live/runtime and human walkthrough results are known.

## 13. Public-release rehearsal

Before changing repository visibility:

- perform a fresh clone into a clean environment;
- follow only the published instructions;
- install approved optional integrations from their upstream links;
- exercise startup, a small task, checkpoint/restart, and wrap-up;
- run the standardized live-runtime rehearsal separately for every named runtime whose release gate is still open or will otherwise be claimed;
- review licenses and attribution one final time.

Pass condition: the project works as documented without access to any private maintainer resource, and every claimed live-runtime result has an independently verified rehearsal report retained in the canonical evidence register.

The private automated rehearsal now covers the clean checkout, fresh workspace, startup, checkpoint/recovery, runtime bridge generation, wrap-up, local Git transport and live approved installer source. Publication still requires the live-runtime gates that remain open in `evidence/runtime_harness_register.json`, the nontechnical human walkthrough, final privacy review and final provenance commitment listed in `PROJECT_CHECKLIST.md`.

## 14. R6 scoped recall and reviewed activation

Use synthetic source trees and a fake provider; do not access a user's live memory.
`tests/test_r6_retrieval_activation.py` covers deterministic tree identity excluding
Git metadata, post-scan mismatch refusal, unbound legacy entries, retained-report
changes, active drift exclusion at startup/doctor, POSIX read-only files, hard-link
alias refusal, bounded oversized-source review and mutation during publication.

Recall coverage checks two project/client corpora, project IDs overriding a default
wing, unknown/unscoped refusal before provider execution, explicit broad-search
warning, escaped controls and fake delimiters, provider errors and unverified labels.
Scoped wake-up must not call native provider wake-up that includes global identity.

Activation coverage checks read-only session refusal, one shared writer revision and
receipt, same-commit replacement rollback, and the retained R5 fresh-process crash
boundaries, including the immutable operation record. Recovering a committed
activation must not create another revision. Existing supply-chain tests remain gates.

Pass means these exact adapter/controller behaviors passed on the recorded head.
It does not certify arbitrary provider implementations, third-party safety, physical
power-loss durability, current fact mapping before S4 or native Windows lifecycle.
Hosted acceptance and the red baseline are recorded in the architecture checklist.

## S3 lifecycle gate

Exact implementation `d748ca4cb9c9a68ea6afd0dd940964940ea68811` passed workflow
`36897056292`: Linux 314 tests, Ubuntu/macOS Python 3.10/3.14 portability 279 each
(two skips per macOS job), and Windows unsupported-write refusal. Stable local
full suite passed with one expected skip. Twenty lifecycle regressions cover
synthetic Git updates/checks, failed-update rollback, archive/provenance corruption,
concurrency, local skill copying, exact synthetic finding acceptance, advisory
preservation, authority refusal and fresh-process recovery at nine boundaries.
Eight context scanner regressions passed the earlier checkpoint gate
`36883836912`. No actual Superpowers finding was accepted; REVIEW blocks activation.
These gates do not prove native Windows lifecycle, runtime instruction compliance
or provider ingestion. S4 owns optional recall configuration/indexing evidence.
