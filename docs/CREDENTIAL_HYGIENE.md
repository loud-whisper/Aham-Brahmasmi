# Credentials for optional integrations

Repository credentials belong to the platform's login tool. An integration must
look them up when it runs rather than save a key in a script, hook, settings file,
Brain configuration or command argument. Core Aham operation needs no repository
token and does not require GitHub CLI.

## GitHub

Sign in using the independently installed GitHub CLI:

```text
gh auth login --hostname github.com
gh auth status --hostname github.com
```

Launch a trusted client through the optional credential adapter:

```text
PYTHON aham.py integration run --platform github -- gh api user
```

For a client that expects a different credential environment variable:

```text
PYTHON aham.py integration run --platform github --token-env GITHUB_TOKEN -- CLIENT ARGUMENTS
```

Replace `PYTHON` with the installed supported interpreter, and `CLIENT ARGUMENTS`
with the installed client's executable and literal arguments. Choose only a
trusted client: it receives the credential and controls its own output and storage.
Do not use an environment-dump command as a credential test.

Each invocation captures `gh auth token --hostname HOSTNAME` in memory. It uses
the host's active login, has a ten-second lookup timeout, and passes the result to
only the selected child process's environment. It neither prints the token nor
writes it to configuration. Lookup errors suppress both credential-tool output
streams and do not launch the client. Client output is inherited and its exit
code is returned. The launcher passes an argument list without invoking a shell.

The adapter removes inherited `GH_TOKEN`, `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`
and `GITHUB_ENTERPRISE_TOKEN` before lookup and launch, so an old environment
assignment cannot override the new login. It also removes GitHub debug settings.
`--token-env` must name a credential variable ending in `TOKEN` or `KEY`.
The default is `GH_TOKEN` for github.com and ghe.com subdomains, otherwise
`GH_ENTERPRISE_TOKEN`. The child also receives `GH_HOST` set to the selected host;
configure its repository and explicit host arguments for that same destination. Use `--hostname HOSTNAME` for another GitHub host; supply
only a hostname, without a URL, port or path.

Aham does not parse the CLI's credential files. GitHub CLI owns its login storage;
its documented fallback can be a plaintext file when the system credential store
is unavailable. Check `gh auth status` and fix credential-store access before
assuming the login is stored securely. Do not copy that file into Aham. The adapter
does not accept a token value, token file or static-key fallback. Another platform
needs its own reviewed login-tool adapter; unsupported platforms fail explicitly.

There were no repository-token consumers in the framework before this adapter.
Existing local Git history and semantic recall remain unchanged. Integrations
added later that need a repository token must use this lookup boundary (or their
platform's own login tool directly), with no persisted token fields.

## Check managed configuration

```text
PYTHON aham.py check --workspace WORKSPACE --project PROJECT --json
```

The check reports `Credential hygiene` warnings with a relative file location and,
where available, line number. Values and matching text are omitted in both JSON
and human output. The same redaction covers other doctor findings, such as runtime
names, so a separate diagnostic cannot echo a detected secret shape. The check
changes no files, logins or credentials.

Selected workspace coverage is `BRAIN.json`. Selected project coverage is:

- `.aham/runtime.json`, `.aham/runtime.md`, `.aham/command-guard/config.json`;
- `.claude/settings.json`, `.claude/settings.local.json`;
- `.codex/hooks.json`, `.codex/config.toml`;
- `.gemini/settings.json`, `.mcp.json`.

These known integration settings are checked even when malformed or when the
bridge is absent. The check does not recursively search projects, user homes,
platform login stores, Git history or unrelated data. Symlinks/reparse points,
hard links, nonregular files, unreadable/invalid-UTF-8 files and files over 2 MiB
are reported as not checked. The bounded read prevents oversized configuration
from being treated as clean.

Warnings recognize the project's private-key/GitHub/npm patterns, AWS access-key
IDs, `sk-` secret shapes and long literal credential assignments, including JSON
string escapes. These are heuristics: placeholders may warn and unrecognized or
encoded secrets may be missed. A clean scan does not prove absence of secrets.
Warnings are advisory; doctor readiness still describes durable workspace state,
not credential safety. A warning requires review before sharing configuration.

## Recovery order for an exposed key

1. **Inventory every consumer.** Include integrations, hooks, local scripts,
   scheduled jobs, services and automation. Record which operation each needs to
   perform, without recording the key itself. Keep exposure details private.
2. **Switch every consumer to the new method first.** Establish a replacement
   platform login with the needed access. Replace inline keys and saved key
   settings with runtime login-tool lookup. Remove inherited old-token overrides.
   Do not place the replacement credential in project files or shell arguments.
3. **Test each consumer.** Restart or reload long-running consumers as needed so
   they use the new launch path, then exercise an authenticated operation against
   the intended repository with its required permissions. Check each result;
   launching a process or retrieving a token alone does not prove access works.
   Do not proceed while an inventoried consumer still depends on the exposed key.
4. **Revoke the exposed key.** After every consumer has switched and passed its
   test, have the credential owner revoke the old key through the platform. Check
   each consumer again to catch a missed dependency. Aham never revokes keys.
5. **Review remaining exposure.** Check account activity and any logs, backups or
   Git history that may retain the old value. Coordinate history cleanup with the
   repository owner; removing a current settings value does not erase old copies.

This is the dependency-preserving recovery order. If misuse is ongoing or the
credential owner requires immediate containment, the owner may revoke sooner and
accept the resulting interruptions. Do not delay urgent containment for a rollout.

## Verified public sources

The optional GitHub CLI interface is registered in `third_party/registry.json`.
Protocol/license review is limited to the independently installed CLI; Aham does
not install, copy or activate its source tree.

- [Token command and host/account selection](https://cli.github.com/manual/gh_auth_token).
- [Login storage and fallback](https://cli.github.com/manual/gh_auth_login).
- [Environment precedence, debugging and host selection](https://cli.github.com/manual/gh_help_environment).
- [Reviewed token command source](https://github.com/cli/cli/blob/fa92838bef95fe4a29c1587693885d5e9bdb6cf1/pkg/cmd/auth/token/token.go).
- [MIT license at the reviewed source reference](https://github.com/cli/cli/blob/fa92838bef95fe4a29c1587693885d5e9bdb6cf1/LICENSE).
