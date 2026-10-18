# Optional blast-radius command guard

The owner authorized this separate feature outside the architecture queue. All
existing architecture, human walkthrough, runtime evidence and release gates stay
open. This module must not be imported or required by core startup.

## Design

Use the Python standard library and existing project containment helpers. A shared
classifier recognizes a deliberately narrow literal POSIX command grammar. Known
inspection commands may proceed; supported local file mutations are measured with
bounded traversal. At either configured threshold (defaults: 1,000,000,000 logical
bytes and 10,000 filesystem entries), or when scope is uncertain, only the user
may execute. No command is evaluated to discover its effects.

The project root, its ancestors, system trees, mounts, remote actions, disk/volume
operations, database deletion and remote Git history changes cannot acquire an
agent approval. Variables, pipelines, compound syntax, executable scripts and
unrecognized programs conservatively require user execution. This is an optional
accident guard for cooperating agents, not an OS sandbox against malicious code.

Claude uses its documented native PreToolUse ask result. Codex PreToolUse and
Gemini BeforeTool deny tier 2 with chat instructions. Their explicit approval
command records the user's response, effect and undo plan in private local state.
Approvals expire, are consumed once, and bind runtime, session, exact command,
working directory, limits and target metadata. Reclassification precedes consumption,
so approval can never override tier 3. A wrapper uses the same path and executes
only parsed literal argv, with no shell expansion or inherited stdin.

Installation is explicit, project-local and preserves unrelated settings. It
refuses private paths tracked by Git, symlinks and unsupported platforms. --check
does not write, verifies effective ignore rules/configuration, and distinguishes
configuration evidence from native runtime trust/activation. No tool is installed
and no hook is activated in this development environment.

## Implementation and verification

1. Record official hook input/output/configuration sources, public upstream refs,
   licenses and explicit support limits. Add synthetic regression tests first.
2. Implement classifier and boundary/measurement tests, including equality,
   symlink/hardlink/mount refusal and unknown syntax.
3. Implement hook outputs, private approval audit, exact binding, replay/drift/
   expiry/concurrency refusal, malformed-input denial and wrapper execution tests.
4. Implement installer/check mode, merge/idempotency/preservation and private-state
   tests. Add user documentation and retain upstream verification evidence.
5. Run focused tests, foundation verification and full unit suite. Review the final
   diff for privacy, safety and claims; push the feature branch and open a PR.

Primary review risks: shell grammar tricks, destination overwrite/merge effects,
target drift after approval, unknown hook input shapes, and settings that appear
installed while hooks are disabled. Tests must exercise each of these. Native
runtime trust and time-of-check/time-of-use races remain explicit limitations.
