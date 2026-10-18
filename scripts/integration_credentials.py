#!/usr/bin/env python3
"""Resolve repository credentials through a platform login tool, only at run time."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

from state_io import StateError

TOKEN_VARIABLES = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
LOOKUP_TIMEOUT = 10


class CredentialError(StateError):
    """A login credential could not be obtained without a static-key fallback."""


def validate_hostname(hostname: str) -> None:
    if not isinstance(hostname, str) or len(hostname) > 253 or not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", hostname
    ) or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
             for label in hostname.split(".")):
        raise CredentialError("Use a hostname only, without a URL, port or path.")


def login_environment() -> dict[str, str]:
    env = dict(os.environ)
    # gh gives these variables precedence over its saved login. An old inline
    # token must not silently keep a consumer on the credential being retired.
    for name in TOKEN_VARIABLES:
        env.pop(name, None)
    env.pop("GH_DEBUG", None)
    env.pop("DEBUG", None)
    env["GH_PROMPT_DISABLED"] = "1"
    return env


def repository_token(platform: str, *, hostname: str = "github.com") -> str:
    """Return a fresh lookup; never cache, print, persist or accept a token option."""
    if platform != "github":
        raise CredentialError("No reviewed login-tool adapter exists for this platform.")
    validate_hostname(hostname)
    executable = shutil.which("gh")
    if executable is None:
        raise CredentialError("Install GitHub CLI (gh), then use gh auth login for the selected host.")
    try:
        result = subprocess.run(
            [executable, "auth", "token", "--hostname", hostname],
            env=login_environment(), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, check=False, timeout=LOOKUP_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        # Exception strings and both output streams may contain credentials.
        raise CredentialError("GitHub login lookup failed; check gh auth status and sign in with gh auth login.") from None
    token = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[!-~]{1,4096}", token):
        raise CredentialError("GitHub login returned no usable credential; check gh auth status and gh auth login.")
    return token


def run_integration(platform: str, command: list[str], *, hostname: str = "github.com",
                    token_env: str | None = None) -> int:
    """Launch an explicitly selected trusted consumer, passing a token via env."""
    validate_hostname(hostname)
    if not command or any(not isinstance(arg, str) or "\0" in arg for arg in command) or not command[0]:
        raise CredentialError("Supply an integration executable and its literal arguments after --.")
    if token_env is None:
        token_env = "GH_TOKEN" if hostname.lower() == "github.com" or hostname.lower().endswith(".ghe.com") else "GH_ENTERPRISE_TOKEN"
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*(?:TOKEN|KEY)", token_env):
        raise CredentialError("The credential environment variable must end in TOKEN or KEY (for example SERVICE_TOKEN).")
    token = repository_token(platform, hostname=hostname)
    env = login_environment()
    env[token_env] = token
    env["GH_HOST"] = hostname
    try:
        # No shell expansion, credential in argv, global environment update or
        # settings write. The selected consumer owns its own output and storage.
        return subprocess.run(command, env=env, check=False).returncode
    except OSError:
        raise CredentialError("The integration could not be launched; check its executable and permissions.") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run", help="Launch a trusted integration with a credential from its platform login")
    run.add_argument("--platform", choices=("github",), required=True)
    run.add_argument("--hostname", default="github.com")
    run.add_argument("--token-env", help="Consumer's credential variable; defaults to the host's GH token variable")
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return run_integration(args.platform, command, hostname=args.hostname, token_env=args.token_env)
    except CredentialError as exc:
        print("INTEGRATION CREDENTIAL FAILED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
