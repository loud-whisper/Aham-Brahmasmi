# R5 working TODO and resume handoff

Updated: 2026-10-01

This is the active working list for R5 Platform and Git-environment hardening. `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` remains the controlling milestone checklist. Do not mark its R5 boxes complete until final acceptance evidence passes.

## Current verified pre-merge status

The PR description records the completed guest reboot proof: attempt 2 of workflow `35525534797` at `63a4ce4b919f7fa31c8380dab5f391d96681121d` passed Foundation and Linux Python 3.10/3.14 after the runner reconnected. The older reboot-pending notes below are historical and superseded by this evidence.

On 2026-10-01 the runner was offline. The maintainer confirmed hosted allowance
is available and authorized macOS acceptance plus a Windows boundary check.
D1 is resolved in favor of executing the macOS endpoint suite. Local Foundation
passes; the expanded portability suite passes 196 tests with one skip. No local
result is represented as native macOS, native Windows or endpoint-Python evidence.

Pre-merge privacy cleanup removes infrastructure values from the current files. It does not remove values retained in historical PR commits. The isolation probe now requires the repository variable `AHAM_RUNNER_BLOCKED_TARGETS`, without printing target values. Only the maintainer may configure repository settings. No Actions run was started during this inspection.

## Active branch and PR

- Branch: `fix/r5-platform-git-hardening`
- Draft PR: #43
- Base `main`: `e33a9de764888694e18d2cfcfb1590b4938eb750`
- Latest exact-head Linux acceptance head before this handoff update: `50c3470fc11fc2b156365fb6bd438eca487a8aa3`.
- Do not work directly on `main`.

## R5 requirements

### Supplementary findings triage for final acceptance

- F2: interpreter-specific recovery commands belong to A1's single entry point;
  per-platform installation wording belongs to R7. Native Windows remains unsupported.
- F5: hard-link refusal is reproduced by the immutable-publication regression:
  no operation file or temporary publication file remains. R5 now explicitly
  limits supported storage to local filesystems providing hard links, atomic
  replacement and POSIX locks. Early setup/doctor storage diagnostics belong to
  R7's prerequisite and actionable-error work. No removable/cloud/network claim is made.
- F6: the writer documentation explicitly states the macOS fsync/F_FULLFSYNC
  distinction and best-effort directory synchronization. No physical power-loss
  certification is claimed by process-interruption tests.
- F8: the new checkpoint regression creates case variants and composed/decomposed
  accented project names and proves distinct stable identities and checkpoint heads.
- F9: Aham-owned snapshots neutralize inherited line-ending conversion. A user's
  separate Git client is outside that transport boundary; template policy and
  native Windows checkout testing remain W1 work. Portable restore still verifies bytes.
- F12: verified sync-root heuristics and default-folder guidance belong to R7;
  the R5 filesystem boundary excludes certification of cloud-synced workspaces.
- F13 and F14: setup platform/capability instructions and the no-framework-repair
  instruction belong to R7 as ordered in the public-release plan.
- D9: owner-only setup permissions remain a maintainer decision for R7. R5's
  permission regression covers activation rollback, not multi-user workspace privacy.

### Acceptance test design and cost

The existing portable suite covers lifecycle/concurrency, paths, Git boundaries,
portable restore and activation recovery. The added activation test exits child
processes at all four activation journal boundaries and recovers in a fresh
process, checking the old/new trees and manifest identity. The Windows job tests
native unsupported-lock refusal with an unchanged workspace snapshot, not lifecycle
support. Draft PRs run only the Linux Foundation gate; ready PRs add the Linux/macOS
Python endpoints and Windows boundary. Main pushes do not repeat the platform
matrix. Release rehearsals run only on manual dispatch. Finite job limits bound
each invocation. Keep this branch frozen during the final platform run; record
its evidence in the PR, then merge with an expected-head guard. Checklist/handoff
completion can follow in the documentation reconciliation PR, referencing the
exact tested implementation rather than treating new documentation as tested code.

- [ ] Declare supported Python/platform range and prove the claim with acceptance evidence.
- [ ] Test Linux plus intended macOS support; keep Windows explicitly unsupported until its locking/runtime requirements are implemented and tested.
- [ ] Record the native-hardware evidence boundary: the maintainer has Fedora/Ubuntu access but no Windows or macOS machine. macOS evidence is therefore GitHub-hosted-runner evidence only unless another physical/virtual macOS environment is later obtained; Windows must not be described as personally/native tested.
- [ ] Cover spaces, Unicode, case-insensitive and Unicode-normalization collisions, worktrees, detached HEAD, permissions, inherited Git configuration, hooks/filters, and subprocess timeouts.
- [ ] Prove crash/recovery behavior for external-source activation.
- [ ] Pass the final exact-head Foundation and portability matrix.
- [ ] Only after the exact-head gate passes, update the controlling checklist, update this handoff, make PR #43 ready, review the complete diff, and merge with an expected-head guard.

## Platform evidence boundary

The maintainer's available machines are Linux (Fedora and Ubuntu). There is no maintainer-owned Windows or macOS system available for native end-to-end testing.

For R5 acceptance:

- Linux can be validated on the dedicated local Ubuntu self-hosted runner and, when allowance exists, GitHub-hosted Ubuntu runners.
- macOS validation may use GitHub-hosted macOS runners and must be described as hosted-CI evidence, not maintainer-owned hardware validation.
- Windows durable mutation remains unsupported and untested. A future Windows claim requires a Windows-compatible writer-lock design plus Windows execution evidence.
- Passing hosted CI does not prove every filesystem, security policy, shell, Git build, or hardware configuration on that OS.

## Implemented on the R5 branch so far

1. Added explicit platform/Python policy in `docs/PLATFORM_SUPPORT.md`: CPython 3.10 through 3.14; Linux supported; macOS support scoped to the cross-platform core/durable lifecycle; Windows durable mutation remains unsupported because the writer lock is POSIX `fcntl.flock` based.
2. Added Linux/macOS endpoint CI coverage for Python 3.10 and 3.14, while keeping the full Linux Foundation/Bubblewrap gate separate.
3. Added CI concurrency/cancellation and restricted feature-branch validation to pull-request runs to avoid duplicate/stale hosted matrices.
4. Added portable-path rejection for case-fold and Unicode NFC normalization collisions; spaces and ordinary Unicode round-trip coverage is retained.
5. Hardened Git transport against detached-HEAD snapshots, active clean/smudge filter attributes, inherited automatic CRLF conversion, and unbounded Git subprocesses. Existing worktree/hook protections remain in force.
6. Added durable external-source activation journaling and recovery, including crash points before/after filesystem moves and after manifest commit, plus permission-failure rollback coverage.
7. Added pending external activation to transient/excluded state so Git snapshots and portable exports do not silently capture an unresolved activation transaction.
8. Fixed the macOS `/var/...` versus `/private/var/...` containment alias defect while preserving the managed inner-symlink guard. Regression: `tests/test_r5_path_alias_containment.py`.
9. Added `tests/run_portability_suite.py` so cross-platform endpoint jobs do not run explicitly Linux-only/Bubblewrap-only rehearsal modules.
10. Self-hosted execution exposed two additional explicit Linux-only modules that the portability suite initially missed: `test_m5_live_rehearsal_isolation.py` and `test_m5_rehearsal_sandbox.py`. Run `35523298885` retained the red evidence. Added `tests/test_r5_portability_suite_scope.py` to prevent future drift and updated the exclusion set. Linux Python 3.10 and 3.14 then passed in run `35523433366`.
11. Added `.github/workflows/r5-self-hosted-linux.yml` for the dedicated local runner. It bootstraps Git into the unprivileged runner home without sudo, verifies confinement, checks rootless Bubblewrap, runs the Linux endpoint suite on Python 3.10/3.14, and runs the full Linux Foundation gate.
12. Confirmed Ubuntu 24.04's AppArmor unprivileged-user-namespace restriction was the remaining rootless-Bubblewrap infrastructure blocker rather than a product defect. A one-boot diagnostic `kernel.apparmor_restrict_unprivileged_userns=0` proved rootless Bubblewrap worked as the unprivileged runner account without granting sudo.
13. Installed Ubuntu Noble's packaged `apparmor-profiles` version `4.0.1really4.0.1-0ubuntu0.24.04.7`, copied `/usr/share/apparmor/extra-profiles/bwrap-userns-restrict` to `/etc/apparmor.d/bwrap-userns-restrict`, loaded it, restored `kernel.apparmor_restrict_unprivileged_userns=1`, and manually proved rootless Bubblewrap still works as the unprivileged runner account.
14. Hardened the self-hosted workflow preflight so it now requires the global AppArmor restriction to remain `1`, requires the Bubblewrap profile file to be present, requires no passwordless sudo, and proves rootless Bubblewrap before running Foundation.
15. Run `35524975778` at head `55bc41c6e5fcc40e3b9329e0cb0feacda4f514e8` passed all three jobs with that hardened state: full Foundation, Linux Python 3.10 portability, and Linux Python 3.14 portability.
16. Corrected `docs/PLATFORM_SUPPORT.md` to state that six explicitly Linux/Bubblewrap-specific modules are excluded from the cross-platform suite, matching the enforced regression list.
17. Final self-hosted run `35525329943` at exact head `50c3470fc11fc2b156365fb6bd438eca487a8aa3` passed all three jobs: hardened Foundation, Linux Python 3.10 portability, and Linux Python 3.14 portability.

## Retained R5 evidence

- Regression-first R5 baseline: `3452fdbd301ee5aba4e086e8c0042e1869898f24`.
- Workflow `35476274356`: Foundation stayed green while the new R5 regressions exposed intended missing behavior.
- Workflow `35476743577`: exposed the original portability-suite design problem and the genuine macOS path-alias defect.
- Hosted workflow `35476915713` and later hosted attempts failed before runner allocation because the GitHub Free account had exhausted 2,000/2,000 included Actions minutes. `steps: []`, `runner_id: 0` failures are not product evidence.
- Hosted run `35525332506` at exact head `50c3470fc11fc2b156365fb6bd438eca487a8aa3` again had all five hosted jobs fail with no steps allocated. It is capacity evidence only, not product evidence.

### Self-hosted runner evidence

The repository-scoped runner the runner VM is registered and installed as a systemd service running as the dedicated the unprivileged runner account user.

Validated containment from actual GitHub-dispatched jobs:

- runner user is the unprivileged runner account, home `[runner home]`;
- no passwordless sudo;
- guest IPv6 disabled;
- public GitHub HTTPS reachable;
- home router `[private target omitted]` blocked;
- workstation LAN address `[private target omitted]` blocked;
- libvirt host address `[private target omitted]` blocked;
- visible block storage is only the disposable 35 GiB VM disk plus normal guest loop/ROM devices;
- no host filesystem shares, Docker socket, SSH keys, the private server mounts, or physical storage are exposed.

Evidence:

- smoke run `35522525505`: containment/network/storage smoke passed;
- smoke run `35523079746`: Python 3.10 and 3.14 provisioning passed on the self-hosted runner;
- unprivileged Git bootstrap was demonstrated without granting the runner sudo;
- R5 run `35523298885`: Python 3.14 endpoint exposed two additional Linux-only Bubblewrap modules incorrectly included in the cross-platform suite;
- regression `tests/test_r5_portability_suite_scope.py` was added before the exclusion fix;
- R5 run `35523433366`: Linux portability passed on Python 3.10 and 3.14;
- R5 run `35523872704`: full Foundation plus Linux 3.10/3.14 portability passed under the temporary diagnostic user-namespace relaxation;
- manual hardened probe: with `kernel.apparmor_restrict_unprivileged_userns=1` and the packaged `/etc/apparmor.d/bwrap-userns-restrict` profile loaded, the unprivileged runner account successfully executed rootless Bubblewrap;
- R5 run `35524975778`: hardened preflight passed and all three self-hosted jobs passed;
- R5 run `35525329943` at exact head `50c3470fc11fc2b156365fb6bd438eca487a8aa3`: hardened Foundation passed, Linux Python 3.10 portability passed, and Linux Python 3.14 portability passed.

## Current blocker / exact stopping point

The Linux side is green with Ubuntu's global unprivileged-user-namespace restriction restored to `1`, no general sudo for the runner, the packaged Bubblewrap AppArmor profile active, the complete Foundation/Bubblewrap gate passing, and both supported endpoint Python versions passing.

The durable boot behavior has not yet been proven after a VM reboot. A reboot proof should verify all of the following together:

- `kernel.apparmor_restrict_unprivileged_userns` returns `1` after boot;
- `/etc/apparmor.d/bwrap-userns-restrict` is loaded sufficiently for rootless Bubblewrap to work;
- the GitHub runner systemd service reconnects without manual `./run.sh`;
- IPv6 remains disabled;
- private-network/host isolation remains intact.

The remaining R5 milestone blocker is macOS exact-head acceptance. GitHub-hosted macOS Python 3.10 and 3.14 jobs still cannot execute while the private-repository Actions allowance is exhausted. Earlier zero-runner failures are not product evidence.

## Self-hosted VM state

- VM: the runner VM, Ubuntu 24.04, disposable 35 GiB qcow2.
- Clean offline-install snapshot exists.
- `isolated-network-baseline` snapshot exists from after network isolation and before runner credentials/state.
- MAC `[guest identifier omitted]`, DHCP-pinned to `[private target omitted]`.
- Preferred management path: `virsh console`.
- Runner: repository-scoped to the maintainer's private development repository, label `aham-r5`.
- Runner service: repository-scoped and enabled under the unprivileged runner account in the retained acceptance evidence.
- Guest IPv6 was disabled by persistent guest configuration in the retained acceptance evidence.
- Global Ubuntu user-namespace restriction is restored to `1`.
- Bubblewrap AppArmor profile is installed at `/etc/apparmor.d/bwrap-userns-restrict` from Noble's packaged `apparmor-profiles` source.
- Fedora/libvirt networking lesson is retained in `docs/FEDORA_LIBVIRT_SELF_HOSTED_RUNNER.md`.

## Next actions

1. Prove runner/AppArmor/network persistence across one guest reboot, then rerun or dispatch the self-hosted acceptance workflow to prove reconnect and confinement.
2. Require the final branch head to retain green Foundation plus Linux Python 3.10/3.14 acceptance.
3. When GitHub-hosted minutes/budget are available, run macOS Python 3.10 and 3.14 acceptance on that same exact final R5 head.
4. Review all exact logs. Fix only demonstrated defects, regression first.
5. Only after the full exact-head gate passes, update `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md`, review the complete PR #43 diff, make the PR ready, and merge with an expected-head guard.
6. Do not begin R6 until R5 is merged and the durable handoff is current.

## Do not do next

- Do not start R6 while any R5 checklist item is unchecked.
- Do not merge PR #43 while exact-head macOS acceptance evidence is missing.
- Do not infer a product defect from zero-runner hosted failures.
- Do not broaden Windows claims; Windows durable mutation remains explicitly unsupported and untested.
- Do not describe macOS as native-machine tested.
- Do not install the GitHub runner directly on the private server or the Fedora host.
- Do not grant broad sudo to the unprivileged runner account.
- Do not persist `kernel.apparmor_restrict_unprivileged_userns=0`.
