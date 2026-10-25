# Verified command-hook protocols

The implementation
and fixtures are original to this project. No private workspace or implementation
is an input. Registry approval is limited to protocol integration with a runtime
the user already installed; it does not approve upstream source-tree activation.

## Claude Code

Official [hooks reference](https://code.claude.com/docs/en/hooks), sections
Configuration, Hook locations, Common input fields, Bash, PowerShell, Command hook
fields and PreToolUse decision control:

- Project-local `.claude/settings.local.json`, `hooks.PreToolUse` matcher groups.
- Input: `hook_event_name`, `session_id`, `cwd`, `tool_name`, `tool_input.command`.
- Output: `hookSpecificOutput` with `hookEventName: "PreToolUse"`,
  `permissionDecision` and `permissionDecisionReason`. Uses allow, native ask, deny.
- Match both Bash and PowerShell. PowerShell is explicitly refused by this POSIX
  classifier rather than silently bypassing a Bash-only hook.
- Command handler timeout is in seconds. `onFailure: "block"` requires Claude Code
  2.1.295 or later. The documented ask behavior in auto mode also has a historical
  correction at 2.1.211; require the higher 2.1.295 minimum for this installation.
- All three hook launch commands map a nonzero process/launch result to exit 2,
  which each official hook reference documents as blocking. This covers a missing
  Python interpreter or script. It does not override the runtime's own timeout.
- Runtime settings and other hooks can still constrain commands. Native trust and
  an actual denial test must be checked by the owner; a settings file is not proof.

Public source reference: [dd6bee38458cc3e6dc5f2b16eca1f0f364619ad8](https://github.com/anthropics/claude-code/tree/dd6bee38458cc3e6dc5f2b16eca1f0f364619ad8).
[License reviewed](https://github.com/anthropics/claude-code/blob/dd6bee38458cc3e6dc5f2b16eca1f0f364619ad8/LICENSE.md):
proprietary, subject to Anthropic Commercial Terms of Service. No redistribution.

## Codex

Official [hooks documentation](https://developers.openai.com/codex/hooks), sections
Where Codex looks for hooks, Review and trust hooks, Config shape, Tool coverage,
Common input fields and PreToolUse:

- Project-local `.codex/hooks.json`, `hooks.PreToolUse`, `Bash` matcher. Unified
  `exec_command` also appears as Bash, not as `exec_command` in the hook input.
- Input uses the same common fields and `tool_input.command` string.
- Output uses `hookSpecificOutput.hookEventName`, `permissionDecision` and
  `permissionDecisionReason`. The adapter emits only supported allow/deny decisions.
- PreToolUse ask and several universal fields are parsed but unsupported and can
  fail open. In particular, never use `continue: false`, `stopReason`,
  `suppressOutput` or `permissionDecision: "ask"` here.
- PermissionRequest can let an existing native prompt continue, but it cannot
  create a prompt for every tier-2 command. The guard therefore denies and requires
  an exact logged chat approval instead of pretending PreToolUse supports ask.
- `cwd` is the session directory. The canonical shell input omits per-command
  working-directory overrides. All mutation operands must consequently be absolute.
  Relative changes remain tier 3, including when someone attempts to approve them.
- Timeout is in seconds. The owner must trust the exact current hook definition
  through the runtime. Configuration checks cannot verify that trust.
- Existing-session stdin and specialized paths can bypass PreToolUse; these hooks
  are not complete enforcement. Launching arbitrary interpreters is refused by
  this guard; it does not police a previously running interpreter.

Public source reference: [8c076942cb70fba8e5c4732c23f1faabc4aed484](https://github.com/openai/codex/tree/8c076942cb70fba8e5c4732c23f1faabc4aed484).
The pinned [PreToolUse serializer and parser tests](https://github.com/openai/codex/blob/8c076942cb70fba8e5c4732c23f1faabc4aed484/codex-rs/hooks/src/events/pre_tool_use.rs)
were also read to corroborate the documented wire format and unsupported ask
behavior. [License reviewed](https://github.com/openai/codex/blob/8c076942cb70fba8e5c4732c23f1faabc4aed484/LICENSE):
Apache-2.0. No source or binary copied. No minimum installed Codex version is
asserted without a live runtime verification; use the wrapper when this protocol
is not present in the installed release.

## Gemini CLI

Official [hooks overview](https://geminicli.com/docs/hooks/),
[hooks reference](https://geminicli.com/docs/hooks/reference/) and
[shell tool reference](https://geminicli.com/docs/tools/shell/):

- Project-local `.gemini/settings.json`, `hooks.BeforeTool` matcher groups, exact
  `run_shell_command` matcher. Timeout is in milliseconds.
- Input common fields plus `tool_input.command`. Optional `dir_path` is absolute
  or relative to workspace root, not necessarily the hook process directory.
- Output is a top-level `decision: "allow"` or `"deny"`, with `reason` for denial.
  There is no hook ask result. Its policy engine's separate ask_user decision is
  not a BeforeTool hook output.
- Exit 0 carries one JSON object. Non-JSON stdout or ordinary hook failure can
  fail open upstream. The endpoint reports handled failures as valid deny JSON;
  a process timeout remains a native-runtime limitation. The installed shell
  launcher maps a missing interpreter or other nonzero exit to blocking exit 2.
- Project hook trust, disabled hooks and policy settings remain owner-controlled.
  `--check` inspects local configuration, not all effective runtime settings.

Public source reference: [ed96faedfd5571f055c44f2c9509d62321d1138d](https://github.com/google-gemini/gemini-cli/tree/ed96faedfd5571f055c44f2c9509d62321d1138d).
The pinned [shell documentation](https://github.com/google-gemini/gemini-cli/blob/ed96faedfd5571f055c44f2c9509d62321d1138d/docs/tools/shell.md)
was also read. [License reviewed](https://github.com/google-gemini/gemini-cli/blob/ed96faedfd5571f055c44f2c9509d62321d1138d/LICENSE):
Apache-2.0. No source or binary copied. No minimum installed release is claimed;
use the wrapper if native hooks are absent.

## Local and unknown tools

These existing project runtime profiles receive the explicit wrapper path. No
hook filename, event or output schema is invented for them. The installer accepts
`wrapper` as an execution mode, not as a new runtime capability claim.
