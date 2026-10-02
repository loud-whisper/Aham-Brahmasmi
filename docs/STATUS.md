# Project status and evidence

This project is a public preview. The maintainer authorized publication on
2026-10-02 under release-plan decision D2 option (b): a clearly labeled preview
before the 1.0 gates close. Real newcomer walkthroughs, E1 live evidence and the
offline provenance commitment remain open; passing automated checks is not a
completed human walkthrough.

This public repository starts with a fresh history. Pull request numbers, commit
hashes and workflow run IDs cited below refer to the maintainer's private
development archive, so public readers cannot open them; they are retained as
the recorded evidence trail. The controlling queue is `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md`;
the retained release plan is `docs/PUBLIC_RELEASE_PLAN.md`.

## Implementation checkpoints

M1–M6 and R1–R6, S1–S4 and A1 are merged with exact implementation and test evidence
in the controlling checklist and `docs/dev/CURRENT_WORK_CHECKPOINT.md`. R7's revised
onboarding and diagnostics implementation checkpoint is merged in PR #61;
its human walkthroughs remain open. Exact head `94f88d1` passed workflow
`36915089427`: 390 Linux tests, 355 per Ubuntu/macOS portability job (two skips
per macOS job), and Windows unsupported-write refusal.
D9 owner-only POSIX permissions and D3 native Windows implementation are approved.
W1 merged through PR #64 as `3a5f139a3ac730ee5a19b6b51faa7a95d16ece0d`.
Exact head `1027f70c9c9d62f8edcb849c338feac20eea15c8` passed all six jobs in
workflow `36936673766`: 407 Linux tests, 372 per Ubuntu/macOS job and 372 native
Windows tests plus six concurrency/recovery tests. Native protected ACLs, long
paths, junction refusal and PowerShell passed. Detailed skips, failed evidence
and measured runner time are in `docs/W1_TEST_DESIGN.md`.
R8 repository preparation merged in PR #66 as `8ce128b`.
Exact head `68bfb593831b68a143c182a66ee27c35c635d13f` passed manual Linux workflow
`36938429399`: Foundation, 412 tests (four skips) and offline release rehearsal.
Security/contributor policies, templates, versioning and hardened CI are prepared;
maintainer settings are a checklist only. Final R8 publication gates remain open.
The initial grouped Actions update merged in PR #67 as `f7ef9b3`; official checkout
v7.0.1/setup-python v7.0.0 pins passed all six jobs in `36938855039` at exact head
`bd0aaa750f737161029cd48889a20f99d13fd93d`: 412 Linux tests, 377 per portable/native
Windows job and six Windows concurrency/recovery tests. W1 scope is preserved.
The native core does not imply Linux Bubblewrap isolation on macOS or Windows;
R7 human walkthroughs remain open.

Implemented components include canonical lifecycle writers and receipts, durable
checkpoints and recovery, scoped records, portable backup/restore, optional local
Git, deterministic skill scanning and activation identity, universal skill reading,
explicit skill updates/removal/rollback, scoped MemPalace integration and offline
keyword recall, owner runtime trust/probes/revocation, compact plain commands and
strict chat paste import. Optional components do not become startup requirements.

Superpowers still has unaccepted REVIEW findings and is not activated as a default.
MemPalace approval covers the user-installed CLI interface; its quarantined whole
source scan remains FAIL and cannot be waived. See `docs/SOURCE_REVIEW.md` and
`docs/MEMORY_CONNECTION.md` for scope. No source code is silently installed.

## Runtime evidence

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

These are historical exact-commit results. They do not prove newer code or compact
packet consumption by a live model. Claude live testing is deferred by the
maintainer as of 2026-10-01. An unlisted runtime trust flow and live chat paste
consumption remain E1 follow-ups. The low-context
controller budget test covers the bridge plus compact startup at 12 KiB.

## Remaining release gates

- Complete R7 newcomer walkthroughs with real nontechnical testers.
- Preserve W1’s verified platform scope; see `docs/PLATFORM_SUPPORT.md`.
- Complete E1 live runtime follow-ups as budget allows, preserving single-run scope.
- Complete final R8 all-branch/all-PR and current-tree privacy review, maintainer
  settings, offline provenance commitment and final release audit.
- Obtain explicit maintainer publication authorization after the gates pass.

`PROJECT_CHECKLIST.md` tracks the broader phases, `docs/TEST_PLAN.md` the acceptance
tests, and `evidence/runtime_harness_register.json` the runtime evidence. Internal
working notes live under `docs/dev/`. A planned change is never evidence of completion.
