# Current work checkpoint

Updated: 2026-10-02

## Resume here

2026-10-02: published via route B. This repository is the public preview with a
fresh history; the original repository was renamed and kept private as the
development archive (its runner, history, workflow runs and PR evidence stay
there). PR, commit and run IDs in this file refer to that archive. The
maintainer authorized the preview under release-plan decision D2 option (b).
Open 1.0 gates are listed at the end of "Release-readiness audit 2026-10-02".
Never push the archive's history to this repository.

W1 is merged in PR #64 (`3a5f139`) with all six exact-head hosted jobs green;
evidence checkpoint PR #65 merged as `728f228`. R8 repository/CI preparation
PR #66 merged as `8ce128b226edde8a069bd0df9c50eb934fa184a6` after exact-head
manual Linux gate `36938429399` passed Foundation, 412 tests and offline audit.
Evidence PR #68 merged as `0f64b74`. The initial grouped Actions update PR #67
merged as `f7ef9b3ce240907af2346c1cc7ded4cc670f2d79` after all six jobs in
`36938855039` passed at exact head `bd0aaa750f737161029cd48889a20f99d13fd93d`.
Latest pins are checkout v7.0.1/setup-python v7.0.0; no platform behavior changed.
Earlier in-progress sections below are retained historical checkpoints.

Remaining work: R7 real newcomer walkthroughs; E1 unlisted-runtime and chat
paste-mode live evidence; final R8 privacy/history scan and human review,
maintainer settings, final-tree release audit and fresh offline provenance.
The maintainer deferred E1 live Claude testing on 2026-10-01. Do not infer a
deferral of other live evidence or fabricate results. The public preview is authorized
(see above); use `docs/MAINTAINER_PUBLICATION_CHECKLIST.md` for the 1.0 release.
The next independent work must follow these remaining gates on a separate branch.
Work solo; save/push/PR/merge every verified checkpoint. The final section records
this checkpoint's documentation verification.

## Verified state

R5 is complete and merged through PR #43 as
`4a3b0d47c98aa354ef64f14f2e78bf1abbea4989`. The exact tested implementation was
`c480e00073416f254493bfc218a6de1516200e51`; hosted workflow `36861543247`
passed Foundation (231 tests), Linux/macOS Python 3.10/3.14 portability
(196 tests per job), and Windows unsupported-write refusal. The macOS jobs each
skipped two tests. These are the stated CI environments, not universal platform
or physical power-loss evidence. Windows lifecycle was unavailable at R5;
the W1 completion below supersedes that historical boundary.

P0 merged through PR #47 as `e864fc5`, reconciling the retained audit plan,
architecture milestones and project checklist. It changed four documentation files.

The runner acceptance jobs used 359 seconds of wall time across six jobs, or
10 minutes rounding each job up. This is measured runner time, not billing usage.
The unused offline self-hosted run was cancelled. Ready PRs run the platform
matrix; draft PRs and main pushes use the Linux Foundation gate. The live-upstream
release rehearsal is manual. Use hosted minutes only for required gates or a
specific unresolved concern, and record failed evidence instead of retrying blindly.

## R6 completion

R6 merged through PR #48 as `63d5fcf22e55c93b11fc3dfdeba44bb38dba1651`.
The exact tested implementation is `eddff878b2ab328ae1527ee901b5ec539bcd6901`.
Workflow `36866478419` passed all six jobs: 248 full Linux tests, 213 tests per
Ubuntu/macOS Python 3.10/3.14 portability job (two skips per macOS job), and native
Windows unsupported-write refusal. Draft Linux workflow `36866244991` also passed.
Post-merge Linux workflow `36866893656` passed on the merge commit.
The original regression baseline
`e16ed7e71a4f9db5068eeb1466ec343db87342c6` failed exactly the 11 new assertions
in hosted Linux workflow `36863810011` (241 tests). It is retained in PR history.
Implementation now binds content/report identity, freezes active POSIX content,
excludes unbound or drifted sources, requires recall scope, escapes recall/errors,
and records activation through writer/session authority and a receipt.
No live user MemPalace data is used by these synthetic tests.

The pinned public MemPalace CLI parser and query implementation were verified at
`25203ed6ee1a739103a77e87219a1f679dee81e9`: search accepts `--wing` and `--results`;
wake-up accepts `--wing` but still adds global L0 identity. Scoped adapter wake-up
therefore uses wing-filtered search; native wake-up needs explicit `--all-scopes`.
R6 labels every recall as unverified until S4 supplies
authenticated committed-record mapping. A provider's text cannot assert its own
authority or current fact state.

Further local red/green evidence covers global wake-up leakage, same-commit
replacement recovery, read-only runtime refusal and missing activation receipts.
The R5 fresh-process crash regression now also covers the immutable activation
operation-record boundary. The final suite has 17 R6 regressions. The acceptance
matrix used 391 seconds across six jobs, or ten runner minutes rounding each job
up. This excludes the separate Linux draft/baseline gates and is not billing usage.
No extra platform rerun or live-upstream rehearsal was needed. Existing semantic-provider configuration has
not been migrated here; S4 owns its connection transaction and per-project mapping.

## S1 completion

PR #50 merged as `4e2d68ad13cefc927539ae7a68063bc72a282270`. Exact implementation
`de9c1eaec9de42ee2cbfcec7337c186fbc0cc660` passed all six jobs in workflow
`36873888390`: 273 full Linux tests, 238 tests per Ubuntu/macOS Python 3.10/3.14
portability job (two skips per macOS job), and native Windows unsupported-write
refusal. Draft Linux `36873457417` passed too. The original red baseline
`7a24c25413cf906ca37a5968993dfd5f90c482f8` failed exactly 18 new assertions in
`36867861182`. Expanded local failing cases preceded implementation; the final
suite has 25 S1 regressions and the stable local 273-test run passed.

The implementation covers bounded deterministic rules, escaped findings, stable
identities, diff-aware updates, opt-in advisory packets, registered external adapters,
explicit human acceptance through the ledger and receipts, and mandatory activation
rechecks. Content or rule changes void acceptance. FAIL and incomplete scans cannot
be waived. D5/D6 are approved opt-in features; no third-party scanner is installed
or registered by default. No private Brain code/data or live user memory was used.

The local network-gated release rehearsal scanned the exact public Superpowers pin
without executing its content. Its lifecycle passed and the scanner returned FAIL,
with activation blocked and all 160 findings accounted for in
`docs/S1_SCANNER_EVIDENCE.md`. Three FAIL findings are potential contextual false
positives; rules were not weakened and no agent waivers were issued. Superpowers
could not activate under the S1 rule pack. The S3 checkpoint below records the
tested context corrections; unaccepted REVIEW findings still block activation.
`docs/SKILL_SCANNER.md` documents contracts and limits. The matrix used 412 seconds
summed runner wall time, or 11 minutes rounding each job up. That excludes separate
Linux baseline/draft gates and is not billing usage.

## S2 completion

PR #52 merged as `74633e0ad7874696388bb199e0a47d57638af5db`. Exact corrected
head `476222da518776a2cde714523bbbf185c2387f97` passed all six jobs in workflow
`36879782673`: 286 full Linux tests, 251 tests per Ubuntu/macOS Python 3.10/3.14
portability job (two skips per macOS job), and Windows unsupported-write refusal.
Post-merge Linux `36880721381` passed too. The original baseline
`2d3e0597f3de0a717840e371c6f2bea95ee364eb` failed exactly two new assertions and
five missing-module errors in `36875603316` (280 tests, Foundation passed).

Implementation `1be1baa` passed 285 local tests and hosted Linux `36877889562`.
Initial matrix `36878736815` passed Linux/Ubuntu/Windows but exposed a macOS
temporary-directory parent alias. A local POSIX regression reproduced the same
relative-path error before the canonical-root fix. The corrected stable local run
passed 286 tests; the final suite adds 13 S2 regressions. One corrected-head matrix
was needed. Initial/final matrices used 420/483 summed runner seconds, or 11/12
minutes rounding each job up; these exclude draft/baseline gates and are not billing.

Skills derive from committed activations, current content identity and ledger
preferences. Activation/preference writers materialize the revisioned index and
populate BRAIN's existing skills field as a nonauthoritative compatibility summary.
Project overrides and read-only refusal are enforced. Context uses bounded qualified
names/descriptions, omits disabled/drifted skills, and isolates optional metadata
failure and revision mismatch. Cached edits cannot inject descriptions or grant
preferences. The universal bridge preserves user/lifecycle/writer authority and
requires reading the full skill before use; scripts still need user approval.
D4 is approved: native copies are deferred. No global configuration was changed.
Contract/layout evidence: `docs/SKILL_INDEX.md`; test design: `docs/S2_TEST_DESIGN.md`.
At S2 completion the public Superpowers pin had 14 supported skill folders but
its S1 FAIL blocked actual activation. No new live runtime consumption is claimed.

## S3 scanner checkpoint

D8 is resolved: review Superpowers first; defer additional default collections.
PR #54 merged as `5c1723a78b01af8156a3fbdc705b091181f8d62d`. Exact tested
implementation `9dff88db264eadabea07bc9c7c037d9e14e41fe6` passed all six jobs
in workflow `36883836912`: 294 full Linux tests, 259 per Ubuntu/macOS Python
3.10/3.14 portability job (two skips per macOS job), and Windows unsupported-write
refusal. Local red preceded the eight context regressions; the stable full local
suite passed with one expected skip. The ready PR ran one matrix, with no hosted
red or draft gate. It used 520 summed runner seconds, or 13 minutes rounding each
job up; this is not billing usage.

The unchanged Superpowers tree now scans REVIEW: 98 REVIEW and two INFO findings.
Activation remained blocked, with no accepted findings or script/hook execution.
All remaining findings are inventoried in `docs/S3_SOURCE_REVIEW_EVIDENCE.md`.
Corrections distinguish past failure messages, JavaScript environment properties
and full-line shell comments while retaining malicious instruction/read coverage.
The lifecycle gate passed as recorded below.

## S3 lifecycle completion

PR #55 merged as `8c76a10f779f7a9025b33e8805ab4a1cf45a320e`. Exact implementation
`d748ca4cb9c9a68ea6afd0dd940964940ea68811` passed all six jobs in workflow
`36897056292`: 314 full Linux tests, 279 per Ubuntu/macOS Python 3.10/3.14
portability job (two skips per macOS job), Windows unsupported-write refusal.
The stable full local 314-test run passed with one expected skip. The final 20
lifecycle regressions cover every command, failed-update rollback, all five
activation/four deactivation crash boundaries in fresh processes, corrupt archive
payloads, path binding, concurrent updates, local provenance and exact synthetic
finding confirmation. No real source findings were accepted or scripts executed.

Saved red checkpoint `bea559f` preceded implementation. Initial stable 313 tests
passed; a later historical-deactivation payload regression then reproduced a gap,
fixed before the final run. All failures stayed local. One ready lifecycle matrix
used 470 summed runner seconds/11 per-job rounded minutes, not billing usage.
No draft/baseline hosted gate or weekly polling was added. Removal preserves files
in an archive; rollback checks both immutable provenance and current content.
Expected-scan differences raise REVIEW without masking FAIL. Retained advisory
and external findings survive reviewed activation. S3 is complete at framework
level; native Windows lifecycle and live runtime consumption are not claimed.

## S4 completion

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

## A1 completion

PR #59 merged as `c739ad61a359c1d884b21588fe6c71fd4cb70c39`. Exact acceptance
head `7fa757496bc293062031d1013223a65cfdd0b689` passed all six jobs in workflow
`36909749861`: 372 Linux tests, 337 per Ubuntu/macOS Python 3.10/3.14 portability
job (two skips per macOS job), and Windows unsupported-write refusal. Local
Foundation and 372 tests passed with one expected skip on `c6988d1`; the acceptance
commit has the identical file tree. The final A1 suite contains 29 regressions.

Writes now require ledger-backed explicit owner trust, reported write capability
and a successful transient controller probe. Trust is revocable; profile names
grant no authority and degraded mode stays read-only. Plain verbs wrap the existing
controllers. Bounded chat export/import binds workspace, project, base revision
and replay identity, with invalid input rejected before mutation. Real Git/export
tests exclude cache/probes while retained canonical trust survives restore. R1
migration preserves identity without inferring vendor trust; all nine M5 session,
project, revision and recovery regressions remain green.

Local failures reproduced missing interfaces, legacy positive fixtures lacking
explicit trust, project-bound chat forwarding, changed replay base and superseded
setup session output before correction. No failing A1 hosted matrix or blind rerun
was used. The one matrix consumed 616 summed runner seconds, or 13 minutes rounding
each job up; this is runner time, not billing usage. The normal post-merge Linux
workflow `36910222596` passed on the merge commit.

Owner confirmation records intent, not authenticated human identity; application
rules do not sandbox same-permission processes. The writer probe verifies the local
controller backend, not model tools or instruction compliance. Native Windows
lifecycle, live compact-packet consumption and human walkthroughs remain separate
gates. Evidence and instructions: `docs/A1_TEST_DESIGN.md` and
`docs/ASSISTANT_ACCESS.md`.

## Next action

R7 is first unchecked. Its implementation is merged; real newcomer walkthroughs
are pending. D9 and D3 are approved below. Keep human outcomes separate from
automated evidence. The maintainer explicitly authorized continuing W1 on
2026-10-01 while human results remain pending;
continue to preserve A1/S4 authority and recovery and use regression-first tests.

Implementation branch: `test/r7-newcomer-flow`, based on A1 evidence merge
`becad83a9e89c2cbd9197ad54f7a63150cf6606b`. Initial R7 design and nine synthetic
regressions are saved before implementation. Red tests cover permission defaults,
false readiness, pending checkpoint diagnosis, corrupt state, missing onboarding
helpers and unprepared documentation/walkthrough paths. No hosted red gate is used. A corrected permissive-umask harness reproduced the
actual permission assertions. A1 post-merge Linux `36910222596` passed.
Design: `docs/R7_TEST_DESIGN.md`. Human walkthrough outcomes remain pending.

## Remaining order and decisions

R7 -> W1 (per D3) -> R8.
E1 follows A1 when budget allows. D1 is resolved by executed macOS acceptance.
No release-staging change is approved; keep the repository private until the
walkthrough and publication gates pass and the maintainer authorizes visibility.
D9 approved: enforce owner-only POSIX permissions at R7. D3 approved: implement
native Windows support and its hosted gate at W1. Human walkthroughs remain pending. User instruction: work alone,
one milestone per branch/PR, save and merge at green checkpoints for handoff.

## Evidence and privacy boundaries

Do not claim historical live-runtime results prove newer code or compact-packet
consumption. Retain M1-M6 and R1-R4 evidence in the controlling checklist.
The R5 current files are sanitized; old PR commits still require the publication
history review. Do not reproduce private infrastructure identifiers. No repository
settings, runner registration or visibility change is authorized for an agent.
Keep unrelated user work untouched and never stage it for a checkpoint.

## R7 implementation local acceptance

Setup now creates private POSIX content with 0700/0600 modes; doctor diagnoses
missing workspace, pending checkpoints, access modes, platform/Python and corrupt
state. Expanded snapshots caught an existing ledger-read helper creating an empty
operations directory; that helper now reads without creating it. Legacy pending
work with no trust records can obtain explicitly confirmed owner recovery access
limited to recovery operations; it does not grant new work. Internal notes moved
to `docs/dev/` and generated evidence moved to `docs/STATUS.md`. Human walkthrough
outcomes remain pending; no R7 completion is claimed. Implementation save
`6deac0f` is pushed with CI skipped. Final review added regressions for unverified
Windows access and stale-session recovery guidance, after reproducing both faults.
All 18 R7 tests pass; Foundation, four documentation and four reconciliation tests
pass. The stable full local suite passed 390 tests with one expected skip. One
ready-PR platform matrix passed; no hosted red/draft gate was run.

PR #61 merged as `758be6478b2fc5a06bf30a898b9eaa300e9791a2`. Exact acceptance
head `94f88d1053c9479606b25ec9ed2ca2cc9997ab27` passed workflow `36915089427`
with all six jobs green: 390 Linux tests, 355 per Ubuntu/macOS Python 3.10/3.14
job (two skips per macOS job), Windows unsupported-write refusal. The matrix
used 599 summed runner seconds or 13 minutes rounding each job up, not billing
usage. Normal post-merge Linux `36915526237` passed; no duplicate dispatch.

All four R7 human acceptance boxes remain open. Walkthrough protocol and blank
template are under `docs/dev/`; no humans were contacted or outcomes fabricated.
The maintainer's 2026-10-01 "Continue" reply authorizes proceeding with W1 while
human results remain pending, resolving the ordering question under AGENTS.md.
D3 approval remains valid. Keep the repository private and human boxes open.
PR #62's evidence merge is `e60cb601507558548674bffe0476f80f000c46ad`.
No open PRs remained at the live resume check. Resume checkpoint branch:
`docs/w1-resume-checkpoint`; next implementation branch: `feat/w1-native-windows`.
Design cross-process contention/crash and lifecycle tests before changing the
Windows gate. Run local synthetic tests first; one final ready PR matrix is the
planned hosted acceptance. Do not claim native Windows support before its
real hosted portability and Astra F4 concurrency results pass.

## W1 implementation in progress

Active branch: `feat/w1-native-windows`, based on resume-checkpoint PR #63 merge
`cebd811` (ordering approval and R7 post-merge success). Red design save `22ee7c3`
is pushed with CI skipped. Twelve new regressions cover locking, killed holders,
Windows-invalid portable/managed paths, reparse containment, script providers and
PowerShell command quoting. Native junction and PowerShell execution checks skip
on POSIX and must run on hosted Windows. Local targeted suites pass. Full local
acceptance and native hosted matrix are next; no native support claim yet.

The Windows job now runs Astra F4 concurrency/recovery and the full core portability
suite instead of refusal only. Both missing lock backends are still tested for
zero-mutation refusal on every host. Windows locking uses byte zero of a persistent
file, nonblocking contention retries and a 30-second timeout. POSIX flock remains.
Windows ACL privacy is not inferred from chmod; doctor labels that unverified.
Test design and primary references: `docs/W1_TEST_DESIGN.md`. No Actions run yet
for W1. Save implementation before the full suite; do not change HEAD/tree while
live-isolation fixtures are running.

Initial W1 PR #64 head `7f7ec6ff9bfb08325e57d02457d70fe4b9b7170d`, workflow
`36933452297`, passed Linux (402), Ubuntu (367 each), and native Windows Astra
F4/recovery (six). Both macOS jobs failed two unresolved-path fixture assertions;
Windows core failed those two plus trailing-dot validation (367 tests, nine skips).
Local TMPDIR alias and injected native-normalization reproductions preceded fixes.
Failed evidence is retained; no blind hosted retry or rerun was requested.

The W1 plan's ACL requirement is now implemented with native security APIs:
protected roots admit current user, SYSTEM and Administrators; unsafe existing
folders are refused, and doctor diagnoses drift without changing permissions.
Backup/restore staging is private before data copying. Seventeen W1 regressions
pass locally (four native-only skips), including ACL policy and setup lexical
refusal. Native protected ACL, long-path, junction and PowerShell cases must pass
on the corrected hosted head. Full local acceptance is next. Preserve current
branch work remotely with CI skipped before spending the corrected matrix.

## W1 completion and next action

PR #64 merged as 3a5f139a3ac730ee5a19b6b51faa7a95d16ece0d. Exact head 1027f70c9c9d62f8edcb849c338feac20eea15c8 passed all six jobs in workflow 36936673766: 407 Linux tests (four skips), 372 per Ubuntu/macOS portability job (four Ubuntu/six macOS skips), and 372 native Windows core tests (nine skips) plus six independent-process concurrency/recovery tests. Windows Python 3.14.7 on the hosted local filesystem passed protected ACL creation/drift, long paths, junction refusal and literal PowerShell execution. The matrix used 997 summed runner seconds, or 20 minutes rounding each job up; these are measured runner times, not billing usage.

The older W1 in-progress paragraphs above are historical checkpoints, superseded
by this exact acceptance. PR #64 is merged; normal post-merge Linux gate
`36937427864` passed on `3a5f139a3ac730ee5a19b6b51faa7a95d16ece0d`.
R7’s four real human acceptance boxes remain open. Next: R8 repository preparation
on a separate branch. Contributor Covenant standard policy is approved; its project
reporting contact was supplied by the maintainer for the R8 policy. Prepare maintainer
settings as a checklist only. No visibility change, runner removal, history deletion,
public tag/release, external messages or final offline provenance-secret generation
is authorized. E1 live-model evidence remains open. Keep working alone and save,
push, PR and merge each green checkpoint.

## R8 preparation in progress

W1 evidence PR #65 merged as `728f228be3377b826844087b56b9c1bf82587680`.
Active branch: `feat/r8-publication-preparation`. Red design/policy save `b6132e4`
is pushed with CI skipped. Five policy tests reproduced 14 assertions and one
missing Dependabot-file error locally before implementation. They now pass.

SECURITY, threat model, CONTRIBUTING, Contributor Covenant 2.1 by-reference policy,
issue/PR templates, Unreleased CHANGELOG and versioning rules are prepared.
The maintainer designated the reporting email for project policies. Official
action tag refs were fetched live: checkout v4 `11d5960a326750d5838078e36cf38b85af677262`
and setup-python v5 `a26af69be951a213d495a4c3e4e4022e16d87065`. Workflows pin those
refs, use explicit per-job contents:read and discard checkout credentials.
Dependabot covers Actions only, monthly, one open PR with grouped updates.
The obsolete self-hosted workflow file is retired; actual runner removal remains
a maintainer checklist item. Manual rehearsal installs Bubblewrap, retains strict
Linux isolation and defaults to offline audit, with live-upstream opt-in.

Next: stable local full acceptance, save/push, then one manual hosted Linux
rehearsal on the exact branch; create/merge the preparation PR after it passes.
Do not spend another Windows/macOS matrix for unchanged platform implementation.
Retain R7/E1 and final privacy/history/provenance/publication boxes as open.
All-branch/all-PR privacy scanning must be repeated immediately before publication
after the final tree is settled; do not claim the preparation scan is that gate.

## R8 preparation completion and handoff

The in-progress R8 section above is superseded by PR #66's merge `8ce128b`.
Exact saved head `68bfb593831b68a143c182a66ee27c35c635d13f` passed hosted manual
Linux run `36938429399`: Foundation, 412 tests (four skips) and offline release
rehearsal. Full local 412 tests passed with five skips. The one hosted job used
121 runner seconds/three rounded minutes, not billing usage. PR/merge used
`[skip ci]` after this explicit gate; normal post-merge Linux `36938774468` also
passed on `8ce128b`. The live run result supersedes the earlier assumption that
the merge body would suppress that push gate.

Final documentation branch: `docs/r8-preparation-checkpoint`. Foundation, four
documentation/four reconciliation tests, five CI policy tests and diff checks
passed before this checkpoint was saved. No full matrix is needed for these
evidence-only updates. The branch includes the user’s live-Claude deferral,
the verified reporting contact decision and the remaining human/release gates.
No account settings, runner registration, branch/history deletion, public release
or provenance secret was changed. No live model call or human outreach occurred.

## Final Actions update checkpoint

The dependency-update head was verified against official upstream tags and local
Foundation/policy checks, then the existing six-job automatic matrix passed:
412 Linux tests; 377 per Ubuntu/macOS/native Windows job; Windows concurrency and
recovery six. PR #67 is merged, and evidence checkpoint #68 is merged. No duplicate
dispatch or blind retry was used. The automatic matrix used 1005 runner seconds/
18 rounded minutes, not billing usage. Monthly grouped updates retain a one-PR
queue; no scheduled test or live-upstream polling was added.

Normal post-update Linux gate `36939643284` passed on `f7ef9b3` before
this final evidence checkpoint merged. Final documentation branch:
`docs/final-actions-checkpoint`. Keep all remaining human/live/publication gates
open as listed under Resume here. Repository visibility was verified PRIVATE.

## Release-readiness audit 2026-10-02

Audited tree: `main` at `6ecdec0` plus branch `claude/optimistic-allen-hgdpfg`.

Fixed on that branch, each with a test:

- `aham.py save --help` and `aham.py wrap-up --help` printed nothing and exited 0.
  `checkpoint.py`/`wrap_up.py` capture core stdout, and argparse's help was lost
  when `SystemExit` left the capture. Help and wrapper-only options now print.
- `setup` named an internal script as its next step; it now names
  `aham.py check --workspace WORKSPACE`, matching user documentation.
- 22 relative links in `docs/dev/reviews/2026-09-18-astra-architecture-review.md`
  were one directory short after the file moved under `docs/dev/reviews/`.
- Added `.github/FUNDING.yml` (GitHub Sponsors and Ko-fi, keys verified against
  the public `github/docs` source) and matching README links.

Local evidence (not hosted CI): Foundation passed; 413 Linux tests ran as an
unprivileged user with rootless Bubblewrap, 411 passed with 4 skips. The two
failures (`test_m5_rehearsal_sandbox`, `test_m5_live_rehearsal_isolation`) were
environmental: that host's `/usr/bin/python3` resolves through
`/etc/alternatives`, which the sandbox does not mount. Hosted Ubuntu links it
directly. Portability suite 378 passed (4 skips); offline release audit passed.
A manual newcomer smoke run (check, setup, trust-runtime, start, save, resume)
verified each step. Running as root or without `bwrap` produces unrelated
failures by design. No symlinks exist in the tree. Every `aham.py` command and
flag named in user docs exists.

Route B was taken on 2026-10-02: route A items (runner, the 20 self-hosted
runs, the personal-email branch, history rewrite) stay inside the private
archive and do not apply to this repository.

Still open for 1.0, none complete; do not mark any from this note:

1. Maintainer: enable GitHub email privacy settings (Settings, Emails).
2. Maintainer: enable Settings, General, Features, Sponsorships; set the About
   description and topics; apply branch protection, fork-workflow approval,
   secret scanning, push protection and private vulnerability reporting per
   `docs/MAINTAINER_PUBLICATION_CHECKLIST.md`.
3. R7 real newcomer walkthrough; E1 live evidence.
4. Fresh offline provenance commitment and final-tree release audit before the
   first tagged release.
5. Low, unresolved: the rehearsal sandbox fails on Debian-family hosts that
   route `python3` through `/etc/alternatives`. Mounting more host state is a
   sandbox-scope decision; record it rather than widening isolation silently.
6. The GitHub Sponsors profile and Ko-fi page were not reachable from the audit
   environment and are unverified.
