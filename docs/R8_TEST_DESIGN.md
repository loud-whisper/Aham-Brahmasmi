# R8 publication preparation test design

W1 and its evidence checkpoint are merged. Real R7 walkthroughs remain open;
the maintainer authorized proceeding and selected Contributor Covenant plus its
project reporting contact. This branch prepares repository content and CI only.
Settings, runner removal, history deletion, offline secrets and publication are
maintainer actions; their acceptance boxes remain open.

Before changing workflows, reproduce mutable action references, inherited token
permissions, persisted checkout credentials, obsolete self-hosted scheduling,
missing manual-rehearsal isolation setup and absent Actions-only update policy.
Five local policy tests enforce those security boundaries. No hosted red gate.

Use official upstream action tag refs to choose full commit pins. Keep version
families unchanged. Give each job only contents:read and make checkout credentials
transient. Retire the obsolete self-hosted workflow file; do not remove the actual
runner registration. Dependabot checks Actions monthly with at most one open PR;
updates still require review and the applicable acceptance gate.

Document the portability runner as the contributor default instead of weakening
the full Linux isolation suite. Make the manual release rehearsal install its
existing Bubblewrap dependency and provide the existing privileged helper in CI.
Default the release audit to offline; live-upstream is an explicit boolean opt-in.
Verify local Foundation/full suite/offline audit before one manual hosted Linux
rehearsal on the saved branch. No duplicate platform matrix is needed for policy
and documentation changes that leave W1's platform implementation unchanged.
Record this scope; it is not a final publication audit or fresh live-model evidence.

Sources checked 2026-10-01: GitHub's secure-use reference, workflow dispatch and
Dependabot options; official action tag refs. Maintainer setting sources are linked
in the publication checklist. Contributor Covenant 2.1 is adopted by reference,
without redistributing its source text or changing the framework source license.

## Preparation acceptance

PR #66 merged as `8ce128b226edde8a069bd0df9c50eb934fa184a6`. Exact head
`68bfb593831b68a143c182a66ee27c35c635d13f` passed manual hosted Linux workflow
`36938429399`: Foundation, 412 tests in 99.905 seconds (four native-only skips)
and offline release rehearsal. Stable local full acceptance passed 412 tests in
101.208 seconds (five skips). YAML parsing and targeted documentation/reconciliation
checks passed. No hosted red/draft gate or duplicate platform matrix was used.
The single hosted job used 121 measured runner seconds, or three minutes rounded
up; this is runner wall time, not billing usage.

This is a repository-preparation checkpoint. Final publication still requires
fresh final-tree checks, all-branch/all-PR scans, human review, offline provenance
and explicit maintainer authorization. The maintainer deferred live Claude testing;
no credential was read, copied or forwarded and no live model result is claimed.

Normal post-merge Linux run `36938774468` passed on `8ce128b`; it is retained
separately from the manual preparation gate. The initial grouped Dependabot update
PR #67 verified official checkout v7.0.1 `3d3c42e5aac5ba805825da76410c181273ba90b1`
and setup-python v7.0.0 `5fda3b95a4ea91299a34e894583c3862153e4b97` against their
upstream tag refs. Removed pip-install input and unsafe privileged-event checkout
changes do not affect this project's inputs/triggers. Foundation and all five
policy tests passed locally before merging. Existing automatic exact-head matrix
`36938855039` passed at `bd0aaa750f737161029cd48889a20f99d13fd93d`: Linux 412
(four skips), portable/native Windows 377 each (four Ubuntu/six macOS/nine Windows
skips), plus six native Windows concurrency/recovery tests. No manual duplicate
was dispatched. The matrix used 1005 summed runner seconds/18 rounded minutes,
not billing usage. PR #67 merged as `f7ef9b3ce240907af2346c1cc7ded4cc670f2d79`.
Normal post-merge Linux gate `36939643284` passed on that merge commit.
