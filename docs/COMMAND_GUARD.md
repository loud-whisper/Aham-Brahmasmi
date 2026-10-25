# Optional blast-radius command guard

This guard classifies shell commands before a cooperating agent executes them.
It is an explicit optional installation. Aham startup, memory and lifecycle work
without it. No tool or hook is installed by normal setup.

| Tier | Agent behavior |
| --- | --- |
| Allow | Run recognized inspection commands. |
| Ask | Describe the measured small change and undo plan in one line. Run only after the user's yes to that exact command. |
| User runs it | Explain the effect and provide the exact command and working directory for the user to run. No agent approval can unlock this tier. |

Default limits are **1,000,000,000 bytes (decimal 1 GB)** and **10,000 filesystem
entries**. A change must be strictly below both. Equality goes to the user. Entries
include directories so enormous trees of empty folders are also bounded. Sparse
files count their logical size; copy/truncate growth is included conservatively.
Traversal is bounded by both the entry limit and a three-second time budget.

## Install and inspect

Run from this framework's checkout, using a user-owned project outside it:

```sh
python3 scripts/install_command_guard.py --project <project-root> --runtime claude
python3 scripts/install_command_guard.py --project <project-root> --runtime codex
python3 scripts/install_command_guard.py --project <project-root> --runtime gemini
python3 scripts/install_command_guard.py --project <project-root> --runtime wrapper
```

Choose the runtime you use; multiple adapters can coexist. Installation preserves
other hook groups and settings. It neither downloads tools nor edits home-directory
configuration. To change the thresholds, supply `--max-bytes` and/or `--max-files`;
omitted values preserve the existing policy. Changing either invalidates outstanding
approvals by changing their binding.

```sh
python3 scripts/install_command_guard.py --project <project-root> --runtime codex --check
```

`--check` is read-only and exits 0 only for the expected local configuration. It
checks private paths, effective Git ignore rules and database integrity. It always
reports `runtime_trust_checked: false`. Review and enable/trust the hook in the
native runtime, then verify one actual denied tool call. A settings-file check is
not proof of runtime activation. Version and protocol details are in
[Verified command-hook protocols](COMMAND_GUARD_SOURCES.md).

Native groups are rendered from `templates/command-guard/hooks.json`. The check
compares the installed managed group against the current template, including its
rendered local command, and reports template or installed-content drift. Unrelated
settings and hook groups remain outside that comparison.

Native installation and wrapper execution currently support POSIX hosts. Claude
requires 2.1.295 or later for the installed failure policy. A PowerShell call is
refused explicitly rather than interpreted as POSIX syntax. No native Windows
execution claim is added.

## What is measurable

The recognized mutation grammar includes literal `rm`, `rmdir`, `unlink`, one
source/destination `mv` or `cp`, numeric-mode `chmod`, simple `chown`, and
`truncate -s BYTE_COUNT`. Supported options are intentionally narrow. Paths must
be inside the selected project, with existing, readable targets; only a copy/move
destination may be missing. Directory destinations that could merge are refused.
Symlinks, hard links, special files, mount boundaries and overlapping targets are
refused. Permission changes measure the subtree conservatively even without -R.

The filesystem root, top-level filesystem folders, selected project root, its
ancestors, system trees, and guard/hook/Git control directories always belong to
the user. Disk/partition/volume operations, database commands, container/cluster
commands, Git mutations including remote history rewriting/deletion, and remote
commands never receive a small-change approval.

Traversal also refuses common database filenames/suffixes and SQLite headers,
including a database nested inside an otherwise small folder. This is conservative
identification, not a complete detector for every database format or live service.
Do not use file renaming or unsupported formats to evade the user-only database rule.

Variables, substitutions, globs, pipelines, redirects, compound commands,
executable paths, scripts, interpreters and unknown programs also go to the user.
This deliberate conservative grammar means even some harmless build or test
commands will need user execution. The guard does not guess a script's effects or
run it to discover them. Split an inspection into a recognized simple command
where useful; never split a dangerous job to evade the thresholds.

Known inspection commands include `pwd`, `ls`, `cat`, `head`, `tail`, `wc` and a
small set of Git status/diff options. Shell metacharacters are refused even when
quoted. Trusted executables, PATH, shell startup files, Git configuration and OS
are prerequisites. An attacker controlling those can change a command's meaning.

Codex's hook reports the session directory and may omit the effective command
directory. Therefore every Codex mutation target must be absolute. An absolute
target must still lie within the selected project; this is not an escape hatch.

## Confirmation and audit

Claude tier 2 returns its native ask result, including the change and undo plan.
Its prompt covers only that pending call; it never receives a chat bypass grant.
For Codex and Gemini, tier 2 is denied with instructions to ask in chat. After the
user says **yes to the displayed exact command**, record that response:

The denial includes the complete, quoted recorder command with the actual session
ID and working directory. Use that supplied command; the generic form is:

```sh
python3 scripts/command_guard.py approve \
  --project <project-root> --runtime <codex|gemini|wrapper> \
  --session-id <exact-session-id> --cwd <exact-working-directory> \
  --command '<exact-command>' --user-response yes \
  --undo '<concrete-restore-or-reversal-plan>'
```

For an agent submitting the recorder through its own hook, use the absolute Python
executable and absolute `command_guard.py` path, include every option above once,
and construct the POSIX command with Python `shlex.join(argv)`. The hook recognizes
only that exact trusted recorder and reclassifies the nested command before
allowing the logging action. Tier 3 can never use this path. There is no broad
environment-variable or persistent yes switch.

Use the session ID from the denied hook's context. A grant lasts five minutes,
is single-use, and binds the exact command bytes, session, runtime, working
directory, policy thresholds and measured target metadata. Retries remeasure;
changed targets need fresh approval, and growth to tier 3 remains denied. The
private SQLite audit records classification, asserted human response, undo plan,
approval and consumption atomically. A consumed approval remains spent if command
execution later fails. Wrapper execution also logs the process exit status.
Claude's native confirmation request is logged; the hook cannot certify the user's
later prompt response or the command's successful completion.

The chat record is the cooperating agent's assertion of a human response, not
cryptographic human authentication. Same-user malicious code can forge assertions,
edit the installation or execute outside it. This feature prevents mistakes under
the stated workflow; it is not an OS sandbox or authorization boundary against a
hostile agent. Launch failures map to blocking exit 2, but native timeouts and
disabled hooks can still fail open in some tools. Keep
the tool's native permissions and isolation enabled.

## Fallback wrapper

```sh
python3 scripts/command_guard.py classify --project <project-root> --command 'rm build/output.txt'
python3 scripts/command_guard.py run --project <project-root> \
  --session-id <session-id> --command 'rm build/output.txt'
```

The wrapper refuses tier 2 until the same logged approval flow completes. It
always refuses tier 3, including when an approval flag or environment value is
supplied. Execution uses the classified literal argv with no shell and no piped
stdin. `--cwd` selects an explicit working directory; the project root is the
default. The wrapper cannot intercept commands sent around it.

## Privacy, recovery and limits

Configuration and command audit are local to `.aham/command-guard/`. The installer
adds ignore rules before writing private paths/data and refuses Git-tracked
private files. Native hook settings hold local interpreter/framework/project
paths and are also ignored. Never publish this directory or the generated native
settings. Existing unrelated settings are preserved. Reinstallation is idempotent;
it refuses a conflicting prior guard definition rather than overwriting it.

To disconnect, remove just this guard's matcher group from the native settings
after reviewing it in the runtime. Retain the ignored state/audit for recovery;
no automatic deletion or pruning is performed. Reinstall/check after relocating
the framework or Python executable. A partially interrupted installation is not
ready until `--check` and a native denial test pass.

Filesystem state can change between measurement and native execution. Metadata
fingerprints detect drift between approval and retry, not every in-flight race,
and do not hash file contents. Other hooks can rewrite a command after this guard;
do not combine it with unreviewed rewriting hooks. Existing interactive sessions,
non-shell file tools and other execution channels are outside this command guard.
Use OS isolation where stronger enforcement is required.

Tests use synthetic temporary projects. Hook protocol tests validate emitted JSON
and generated configuration; they do not claim live authenticated runtime evidence.
