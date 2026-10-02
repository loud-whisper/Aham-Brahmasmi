# Platform and Python support

Aham Brahmasmi separates **portable durable data** from **platform-specific execution guarantees**. A file format being portable does not mean every runtime feature is supported on every operating system.

## Python range

The supported CPython range is **Python 3.10 through Python 3.14**, inclusive.

The lower bound follows the language features used by the framework, including PEP 604 union syntax such as `Path | None`. CI exercises the supported range on Linux, including both endpoints. The project must not claim support for a newer Python release until it has been exercised by CI.

## Operating-system scope

- **Linux: supported.** This is the primary and most extensively exercised environment. The full Foundation suite, including the Linux Bubblewrap isolation gates, runs here.
- **macOS: supported for the model-neutral core and durable workspace lifecycle.** The cross-platform core suite is exercised on a GitHub-hosted macOS runner. Six live-runtime/recovery modules whose subject is the Linux Bubblewrap rehearsal mechanism are excluded from this matrix and remain covered by the full Linux Foundation gate; macOS support does not imply Bubblewrap isolation.
- **Windows: supported for the native core lifecycle in the verified scope below.**
  Hosted Windows Python 3.14 on local NTFS passes the core suite plus independent
  writer concurrency/recovery. Setup, trust, startup, checkpoints, wrap-up,
  recovery, bridges, scoped recall and portable backup/restore run natively.
  Older supported Python versions are code-compatible but have no native Windows
  acceptance evidence here. WSL has no separate verification claim.

### Native Windows boundaries

Writer locking uses `msvcrt.locking` over byte zero of a persistent lock file,
with a bounded 30-second contention wait. Process exit releases the native lock.
Missing lock backends refuse mutation. Managed junction/reparse paths, alternate
streams, reserved devices and trailing-dot/space aliases are refused. Local paths
beyond 260 characters, spaces/Unicode and literal PowerShell arguments are tested.
Python provider scripts use the current interpreter and literal argv, not batch
wrappers. Git-controlled snapshots neutralize automatic CRLF conversion.

Workspace, bridge and backup/restore staging roots are created with protected
ACLs before private data is written. The current owner, SYSTEM and Administrators
are admitted; ordinary other users/groups are excluded. Existing unsafe roots are
refused, and doctor checks without rewriting access. This does not encrypt data or
sandbox administrators, same-user processes or a compromised owner account.
Network shares and Linux Bubblewrap isolation on Windows are not supported.
No physical power-loss or universal filesystem guarantee is claimed.

## CI budget

Draft PRs run the full Linux Foundation gate. Marking the final PR ready also runs
Linux and macOS portability at Python 3.10/3.14 plus one native Windows 3.14 job.
The post-merge push repeats only Linux Foundation, avoiding a duplicate platform
matrix. Jobs have finite time limits. The networked release rehearsal is manual
and should run only for the release gate or a demonstrated integration concern.

This is an evidence boundary, not a product preference. Documentation must not describe the framework as operating-system-neutral without preserving these limits.

## Filesystem portability rules

Portable state must remain representable when moved between common filesystems. Therefore:

- paths containing spaces and ordinary Unicode are supported and regression-tested;
- a portable export refuses two payload paths that collide after Unicode NFC normalization and case folding, because such a bundle cannot be restored unambiguously onto a case-insensitive or normalization-insensitive filesystem;
- managed-path containment accepts equivalent canonical ancestor spellings, such as macOS `/var/...` and `/private/var/...`, while still rejecting symlinked components inside the managed workspace;
- managed paths remain subject to the existing containment and symlink rules;
- linked Git worktrees remain explicitly unsupported for Brain Git transport;
- Git snapshots refuse a detached `HEAD` once commits already exist, preventing a transport-created commit from becoming an easily lost detached commit.

## Git environment hardening

Git transport treats the surrounding Git environment as untrusted input:

- transport-created commits disable hooks;
- initialization uses an empty template rather than inheriting configured template hooks;
- clean/smudge filter attributes on durable snapshot inputs are refused before staging, so an arbitrary configured clean filter cannot execute as part of a snapshot;
- transport Git operations neutralize automatic CRLF conversion where they control invocation;
- external Git subprocesses have finite timeouts and fail explicitly rather than hanging forever.

## External-source activation recovery

Activating a reviewed external source is a small filesystem transaction. R5 adds a durable pending activation record before moving active/quarantined trees. If the process exits after a move but before the installed-source manifest commits, recovery rolls the filesystem back to the last manifest-backed state. If the manifest already records the new source, recovery treats activation as committed and only clears the stale pending record.

The pending activation record is transient recovery state. It is excluded from Git snapshots and portable exports, and portable export refuses to run while such a transaction is unresolved.

## Evidence limits

Passing CI on one hosted image does not prove behavior on every filesystem, Git build, shell, security policy, or hardware configuration. The support statements above mean the tested project behavior is maintained for the stated environments and versions, with documented platform-specific exclusions.

## W1 exact acceptance

PR #64 merged as 3a5f139a3ac730ee5a19b6b51faa7a95d16ece0d. Exact head 1027f70c9c9d62f8edcb849c338feac20eea15c8 passed all six jobs in workflow 36936673766: 407 Linux tests (four skips), 372 per Ubuntu/macOS portability job (four Ubuntu/six macOS skips), and 372 native Windows core tests (nine skips) plus six independent-process concurrency/recovery tests. Windows Python 3.14.7 on the hosted local filesystem passed protected ACL creation/drift, long paths, junction refusal and literal PowerShell execution. The matrix used 997 summed runner seconds, or 20 minutes rounding each job up; these are measured runner times, not billing usage.
