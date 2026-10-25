"""Recovery guidance uses the running interpreter and the public entry point."""
from pathlib import Path
import shlex
import sys


def format_command(arguments: list[str], *, platform: str | None = None) -> str:
    if (sys.platform if platform is None else platform) == "win32":
        return "& " + " ".join("'" + argument.replace("'", "''") + "'" for argument in arguments)
    return shlex.join(arguments)


def recovery_command(verb: str, *, platform: str | None = None) -> str:
    if verb not in {"save", "wrap-up"}:
        raise ValueError("unsupported recovery verb")
    return format_command([sys.executable, str(Path(__file__).resolve().parents[1] / "aham.py"),
                       verb, "--workspace", "<same-workspace>", "--recover-pending",
                       "--session-id", "<active-session-id>"], platform=platform)
