# Command guard test evidence and scope

This optional feature is outside the existing architecture queue with the owner's
explicit authorization. No human walkthrough, runtime rehearsal or release gate
is marked complete by these tests.

## Regression-first evidence

Commit `350b1e8` adds the plan and 18 initial tests before implementation. Running
`python3 -m unittest discover -s tests -p test_command_guard.py` produced 18 missing
module errors. Later focused regressions reproduced three additional defects
before correction: malformed tool names escaped valid-denial JSON, failed launch
returned nonblocking exit 127, and --check accepted a conflicting guard group.
The Codex directory regression also reproduced approval of a relative mutation
against a session directory that cannot establish its effective execution root.
A database-file regression reproduced tier 2 for a small `.db` before database
names and SQLite header identification were added.

## Deterministic acceptance

`tests/test_command_guard.py` has 44 synthetic tests on POSIX.
Its subcases cover:

- all three tiers for all three official native hook output formats;
- exact timeout units, shell matchers, PowerShell refusal and blocking launch exit;
- strict inequality at both thresholds, sparse-file size, copy/truncate growth,
  directory entry count, traversal deadline, permission failures and mount refusal;
- symlink/hardlink refusal, overlapping operands, project escape and control paths;
- disk/partition/volume, database, container, remote Git history and remote-machine
  commands, plus variables, pipes, substitutions, scripts and unsupported options;
- common database files and nested or renamed SQLite databases;
- exact command, session/runtime, metadata drift, policy shrink and expiration;
- one-shot approval consumption by independent concurrent processes;
- the trusted recorder passing its own hook only for an already measured tier 2;
- denial carrying a complete, correctly quoted recorder command, so the agent need
  not guess the runtime's session identity or working directory;
- invalid/non-yes approval, native ask without a chat override, malformed JSON,
  unexpected shell directory fields, corrupted audit state and valid denial JSON;
- wrapper refusal followed by execution only after an exact logged approval;
- no-write check mode, effective Git ignores, tracked-private-file and symlink
  refusal, configuration preservation/idempotency, conflicting guards and disabled
  hooks, and refusal to install into the public framework.

Foundation verification also passes. It checks registry/notices alignment and
obvious public-boundary violations. Automated scans are not a human privacy audit.

## Full suite environment diagnosis

The first full local unit run executed 464 tests: 14 failures and five skips. Every
failure was in existing Bubblewrap rehearsal coverage and reported refusal to
create a namespace. The repository's existing CI namespace-helper path was then
tested on the four sandbox tests: three passed and the isolation case failed at
the environment's privilege-drop boundary. Tests and isolation were not weakened.

The portable suite subsequently passed 432 tests with five existing platform
skips before the final database-identification regression was added. Final hosted
checks must bind the actual PR head, including that last change. The PR records
the final commands, counts, commit and hosted outcomes.

These are synthetic protocol and filesystem tests. They do not certify an
authenticated live Claude, Gemini or Codex session, runtime trust, every OS or
database format, arbitrary shell programs, hostile same-user code, or the absence
of filesystem races. Native installation/execution is scoped to POSIX. Windows
runs pure classification cases and skips installation/execution cases.
