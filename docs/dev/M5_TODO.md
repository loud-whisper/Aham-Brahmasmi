# M5 anti-drift todo

This file is the working todo for architecture-remediation milestone M5. The controlling requirements remain `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md`; `PROJECT_CHECKLIST.md` remains the broader project/release guardrail. If these files disagree, the architecture-remediation checklist controls M5.

## Session authority

- [x] Reproduce Astra F11 before changing behavior.
- [x] Add a durable controller/session authority record with workspace identity, runtime/mode, capabilities, allowed operations, and committed revision.
- [x] Make degraded/offline and unknown/unverified runtime startup issue read-only authority.
- [x] Gate checkpoint and wrap-up through the authority record.
- [x] Restore the full Foundation/unit suite after the first authority implementation.
- [x] Require runtime-started mutators to present the exact issued session ID instead of inheriting whichever workspace-global authority is current.
- [x] Require session revision to match the committed revision before a new mutation, then advance it at the immutable committed-operation boundary.
- [x] Bind project ID when a stable project is selected and record explicit harness/controller identity where relevant.
- [x] Cover checkpoint, wrap-up, and both recovery paths with positive and negative authority tests.

Session-authority evidence: regression-first commit `79588f34b709e08bb8b4b77f92125aa70927dcf3` kept Foundation verification green while workflow `35441269747` reproduced the missing exact-session, stale-revision, and harness-identity controls. The initial exact-revision implementation then exposed its interaction with M2 crash recovery in workflow `35441439628`; authority advancement was moved to the immutable operation-record commit boundary rather than weakening revision equality. Commit `326b265682f6b632eb0a434aa5421bffcb3e0b56` passed the complete Foundation/unit workflow `35441527581`. Extended project-binding, wrap-up, checkpoint-recovery, and wrap-up-recovery tests passed at commit `fa11d4158e60d798d93c4e0a818d935f625f59a7` in workflow `35441614016`.

## OS-enforced rehearsal isolation

- [x] Add a Linux OS-enforced rehearsal launcher using an explicit isolation primitive rather than prompt instructions.
- [x] Use only synthetic rehearsal Brain/project data inside the writable sandbox.
- [x] Keep the real home directory outside the sandbox and provide a synthetic HOME.
- [x] Keep credentials and authentication material outside the sandbox unless a caller explicitly opts in to a specific required mount/value.
- [x] Remove SSH-agent and container-socket access by default.
- [x] Keep unrelated projects and any real Brain outside readable and writable mounts.
- [x] Keep the framework/verifier outside the agent's writable trust boundary.
- [x] Create a harmless outside-sandbox sentinel and prove a sandboxed probe cannot read or alter it.
- [x] Verify the sandboxed agent can still read the read-only framework and mutate only the synthetic project/workspace needed for the rehearsal.
- [x] Document Linux/platform requirements and explicit opt-in escape hatches without broadening the guarantee.

Isolation evidence: a corrected regression-first branch `test/astra-m5-sandbox-regression` at commit `4dffd289f45ba21de498b156117e4836ee62f93e` kept Foundation verification green and failed the unit gate specifically because the OS-enforced sandbox launcher did not exist (workflow `35441878973`). The implementation then exercised Bubblewrap in CI rather than skipping when unavailable. GitHub-hosted runners blocked ordinary unprivileged user/network namespace setup, so after two mechanism-level failures the design was reassessed: the CI-only namespace helper now uses privilege only to construct the mount namespace and invokes `setpriv` before the rehearsal command to restore the invoking UID/GID, clear supplementary groups/capabilities, and set `no_new_privs`. Commit `e726e7b8dfac0012f0f42dbef738fa054005c9fd` passed the full workflow `35442180869`, including the isolation probe for the sentinel, host home, framework write boundary, and container socket.

The real live-rehearsal path was then gated separately. Regression commit `4276366cac4ba0356286b2bf2b421a3d021cd184` kept Foundation verification green while workflow `35443497670` failed because no separate control contract or sandboxed live `run` entry point existed. The implementation separates host `rehearsal.json` and the outside sentinel from a minimal read-only `/control/task.json`, keeps trusted verification outside the sandbox, and requires the generated live instructions to present the startup-issued session ID to checkpoint/wrap-up. Commit `92c496c117919e26513646cfa74b3cc194aa5717` passed Foundation and the complete unit suite in workflow `35443716908`, including a live-wrapper probe that could see the minimal contract/framework/synthetic workspace/project while the authoritative host manifest and sentinel were mechanically absent.

PR review then found two additional explicit-bind containment gaps. Regression commit `90d805e97c5c0df5da3e039aeea28ca235ba6d53` kept Foundation green while workflow `35444112110` reproduced both. The final sandbox rejects protected-tree shadowing, whole-real-home binds, symlink bind sources, non-canonical guest destinations, and duplicate guest destinations; the sole `/control/task.json` exception is read-only and schema-validated.

## Acceptance and merge gate

- [x] Full Foundation verification and full unit suite pass with isolation tests enabled in CI.
- [x] Astra F11 acceptance gate passes for checkpoint and wrap-up.
- [x] Outside-sandbox sentinel is mechanically inaccessible in the exercised rehearsal environment.
- [x] Independent verifier runs outside the sandbox and derives success from artifacts/state, not model prose.
- [x] Cross-check M5 against `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` and `PROJECT_CHECKLIST.md` before checking any M5 item complete.
- [x] Record exact acceptance evidence in the architecture-remediation checklist.
- [x] M5 implementation PR #24 passed complete diff review and fresh PR-context workflow `35444319066` at head `ccc0630044362f30aaa9250d7c20202c62eea997`, then merged to `main` as `d7e9ab758fe9f2754dff179890f9ade966daa263`.

Cross-check note: `PROJECT_CHECKLIST.md` still contains dated historical runtime-result claims. They do not contradict the M5 isolation mechanism, but M6 explicitly requires reconciliation of runtime claims and documentation drift into one evidence source, so those historical claims are not being reinterpreted or promoted during M5.

Do not resume broad runtime/harness comparison work, including DeepSeek Harness, until M1 through M6 are complete.
