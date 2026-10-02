# Filesystem and Git containment

Aham Brahmasmi treats the selected private Brain, the selected project, and the public framework as separate trust boundaries. M4 containment prevents supported lifecycle commands from silently adopting an unrelated Git repository, following pre-existing managed-path symlinks, or writing private runtime paths into a file Git already tracks.

## Brain managed paths

`require_managed_path()` is the shared lexical and symlink containment check for Brain-owned paths. A managed destination must remain below the resolved Brain root, must not contain `..` traversal, and must not contain a symlinked managed component that already exists.

The workspace verifier applies this rule to the required durable files and directories and to known optional state paths. Dynamic paths are also constrained at their owning boundary:

- stable and legacy project files are checked before migration or mutation;
- the project registry and per-project checkpoint heads are checked before read/write;
- operation-ledger records, `store.json`, and the writer lock are checked before use;
- checkpoint destinations and `latest_checkpoint.json` are checked before persistence;
- committed checkpoint references must be a single filename directly below `state/checkpoints/`; traversal-shaped or nested references are not accepted.

A symlinked managed directory or managed file is therefore a refusal condition, not a route to another location.

## Durable-write mechanics

Durable JSON/text replacement uses a same-directory temporary file, file `fsync`, and atomic replacement. Immutable operation records use exclusive temporary creation followed by a hard-link creation that refuses an existing destination. Directory synchronization is attempted after durable boundaries.

On platforms exposing `O_NOFOLLOW`, the writer lock and directory synchronization use it so the final opened object cannot be a symlink. The writer lock is opened directly with `os.open()` and then locked with `flock`.

These controls are designed for a user-owned workspace and protect against pre-existing redirection and ordinary path mistakes. They do **not** claim race-proof isolation from a malicious process running concurrently as the same operating-system user that can continuously replace path components between validation and a later pathname-based content operation. OS-enforced adversarial isolation is an M5 rehearsal/session-authority requirement, not an M4 filesystem claim.

## Git transport identity

Optional Brain Git transport is valid only when `git rev-parse --show-toplevel` resolves exactly to the registered Brain root. If the Brain directory merely sits inside an unrelated parent repository, transport refuses before changing local Git configuration or staging files.

Linked worktrees are detected by comparing the resolved Git directory with the resolved common Git directory. M4 deliberately refuses linked-worktree Brain transport rather than inheriting worktree semantics implicitly. A standalone Brain repository remains the supported transport shape.

Transport commits continue to use the durable-path allowlist and do not run configured Git hooks.

## Private runtime configuration

`.aham/runtime.json` contains machine-local paths such as the framework root, Brain path, and project path. Before runtime-bridge installation mutates `.aham`, the bridge asks Git whether that exact file is already tracked. A tracked private configuration is refused before private paths are written.

Adding an ignore line is not considered proof. When the project is inside a Git repository, installation verifies the effective rule with Git's ignore engine. A later negation or other rule that makes `.aham/runtime.json` effectively unignored causes installation to fail before the private configuration is written.

The M4 audit found `.aham/runtime.json` to be the bridge file containing machine-local/private path values. `.aham/runtime.md` is portable bridge guidance and does not embed those local paths.

## Platform scope

The authoritative writer currently requires POSIX `fcntl.flock`, so durable mutation is not claimed as Windows-compatible today. Linux is the exercised M4 environment. `O_NOFOLLOW` is used when the host exposes it; platforms without that flag rely on the explicit symlink/containment preflight and do not receive the same no-follow open guarantee.

Broader Windows/macOS behavior, case-insensitive path collisions, Unicode filesystem edge cases, and hostile concurrent filesystem mutation remain part of the later platform/rehearsal hardening milestones. M4 does not broaden the project's portability claim.
