"""Read-only platform, private-folder and common sync-root guidance."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import sys


def preflight(*, platform=None, version=None) -> dict:
    platform = sys.platform if platform is None else platform
    version = sys.version_info[:2] if version is None else version
    if platform not in {"linux", "darwin", "win32"}:
        return {"supported": False, "platform": platform, "action":
                "Use a supported Linux, macOS or Windows system; see docs/PLATFORM_SUPPORT.md for the tested scope."}
    if not (3, 10) <= tuple(version) <= (3, 14):
        return {"supported": False, "platform": platform, "action":
                "Select Python 3.10 through 3.14, reopen the terminal if you just installed it, and check the version again. See docs/BEFORE_YOU_START.md."}
    return {"supported": True, "platform": platform, "action": None}


def default_workspace(*, platform=None, home=None) -> Path:
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    # A suggestion only: never create or select it without the owner's choice.
    if platform == "darwin":
        return home / "Library/Application Support/Aham-Brahmasmi/workspace"
    return home / ".aham-brahmasmi/workspace"


def sync_root_warning(path: Path, *, platform=None, home=None, environ=None) -> str | None:
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    roots = [home / "Dropbox"]
    if platform == "darwin":
        roots += [home / "Library/CloudStorage", home / "Library/Mobile Documents"]
    if platform == "win32":
        roots += [home / "OneDrive"]
        roots += [Path(environ[key]) for key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")
                  if isinstance(environ.get(key), str) and environ[key].strip()]
    # Desktop/Documents can be redirected or synced; treat them as a caution,
    # not evidence of an installed sync service.
    roots += [home / "Desktop", home / "Documents"]
    canonical = Path(path).expanduser().resolve()
    for root in roots:
        resolved = root.expanduser().resolve()
        if canonical == resolved or resolved in canonical.parents:
            return ("This location is inside a common sync or Desktop/Documents root. "
                    "Choose a local folder outside cloud sync for the active Brain. "
                    "Detection is a path hint, not proof that sync is enabled; custom roots may be missed.")
    return None


def permission_issue(workspace: Path) -> str | None:
    if os.name != "posix":
        if os.name == "nt":
            from windows_access import permission_issue as windows_permission_issue
            return windows_permission_issue(workspace)
        return "Private folder access cannot be checked on this platform."
    if stat.S_IMODE(workspace.stat().st_mode) != 0o700:
        return "The private workspace directory is not owner-only (0700)."
    if hasattr(os, "getuid") and workspace.stat().st_uid != os.getuid():
        return "The private workspace belongs to another local user."
    return None
