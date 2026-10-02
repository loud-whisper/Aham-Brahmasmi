# Contributing

Read `AGENTS.md`, `docs/PUBLIC_BOUNDARY.md` and the controlling
`docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` before changing behavior. The project is
a public preview; see `docs/STATUS.md` for the gates that remain open.

## Keep contributions generic

Use requirements in this repository and verified public upstream documentation.
Do not copy a personal Brain, private implementation, credentials, user paths or
machine configuration. Use synthetic test data. Respect upstream licenses and
attribution; source proposals require registry review, quarantine and scanning.
Do not add mandatory cloud/provider dependencies to core operation.

Work on a separate branch. For behavior changes, first demonstrate a failing
regression, implement the smallest correction and verify it. Preserve failed
evidence and exact tested commits. Keep unrelated files out of the PR. New behavior
is not complete because a model says it works. Follow `CODE_OF_CONDUCT.md`.

## Local checks

Use your installed supported interpreter in place of `PYTHON`, from the framework
root. No third-party Python packages are required for the core suite.

```text
PYTHON tests/verify_foundation.py
PYTHON tests/run_portability_suite.py
git diff --check
```

The portability suite is the contributor default on Linux, macOS and Windows.
It explicitly excludes six Linux Bubblewrap live-rehearsal/recovery modules;
it is not evidence that those modules ran. On Linux, the full gate also runs:

```text
PYTHON -m unittest discover -s tests -p "test_*.py"
```

The full Linux suite needs Bubblewrap and an environment that permits its isolated
rehearsals. CI installs that dependency and remains strict; do not weaken isolation
checks to obtain a green result. Ask before installing software or using privileged
commands. See `docs/LESSONS_LEARNED.md` for the rehearsal constraints.

## CI budget and checkpoints

Run targeted local regressions and a stable local suite before a ready PR. Draft
PRs and main pushes use the Linux gate; ready PRs run the platform matrix. Use
`[skip ci]` only for saved work/documentation that is verified separately; a code
acceptance must still run on the exact final tree. Do not rerun a failed unchanged
head. Diagnose the failure and consolidate corrections first. Do not dispatch the
networked release rehearsal for ordinary documentation work.

## Reports and pull requests

Use the bug, setup-help or skill-source issue template. Share sanitized diagnostics
and a minimal synthetic reproduction, never private Brain content. Vulnerabilities
use the private route in `SECURITY.md`. The PR template records regression evidence,
commands/results, limitations and upstream sources. Release tags, repository
visibility, account settings and final provenance commitments require maintainer
action after the publication checklist is complete.
