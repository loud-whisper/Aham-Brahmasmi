# Isolated self-hosted Linux acceptance runner

Updated: 2026-10-01

This is a generic record of the R5 runner requirements. Private host identifiers,
network targets, account names and management commands are intentionally omitted.
The framework does not depend on the maintainer's runner or infrastructure.

## Isolation boundary

Use a disposable virtual machine with its own virtual disk. Do not expose host
shares, physical storage, container sockets, host credentials or private server
mounts. Run jobs as an unprivileged dedicated account without passwordless sudo.
Public upstream access and denied private-network access must be verified separately.
A failed outbound connection does not prove private-network isolation.

On the tested Ubuntu guest, rootless Bubblewrap initially failed under AppArmor's
unprivileged-user-namespace restriction. The tested durable solution used the
distribution's packaged Bubblewrap AppArmor profile while retaining the global
restriction. The workflow requires that restriction, the readable profile, disabled
guest IPv6, no passwordless sudo, and a successful rootless Bubblewrap probe.
Do not disable a host security control to obtain a passing test.

## Private probe configuration

The workflow reads the repository Actions variable `AHAM_RUNNER_BLOCKED_TARGETS`
as whitespace-separated private destination addresses. The maintainer supplies
the targets for their environment outside version-controlled files. An absent
variable fails the preflight. The workflow does not print configured targets.
Repository variables are configuration, not a secret store. They do not erase
values from old commits or logs.

GitHub documents the `vars` context and its availability in step environment
variables: https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#vars-context
(verified 2026-10-01).

## Retained evidence

- Workflow `35522525505`: the initial containment and connectivity smoke test.
- Workflow `35523298885`: two Linux-only modules incorrectly entered the portable
  suite; the retained regression protects the exclusion boundary.
- Workflow `35524975778`: Foundation and Linux endpoint-Python acceptance under
  the hardened Bubblewrap policy.
- Workflow `35525534797`, attempt 2, at
  `63a4ce4b919f7fa31c8380dab5f391d96681121d`: Foundation and Linux Python
  3.10/3.14 passed after a guest reboot and automatic runner reconnection.

These runs establish the tested environment only. They do not prove macOS,
Windows, universal filesystem support or a reliability percentage.

## Publication boundary

Before publication the maintainer removes the repository's self-hosted runner
and retires workflows targeting it, then reviews fork-workflow approval settings.
See `docs/dev/R5_REVIEW_FINDINGS.md` for the ordered privacy and history checklist.
Do not attach an unrestricted workstation or private server as a public runner.
