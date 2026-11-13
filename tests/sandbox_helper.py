"""Choose how sandbox tests create namespaces on the current host.

Hosts differ. Some block unprivileged user namespaces, so Bubblewrap needs the
sudo namespace helper. Others confine Bubblewrap with a mandatory access control
profile that removes capabilities from its child, so the helper cannot drop
privileges there while the ordinary unprivileged path works. Tests therefore ask
the host instead of assuming one behavior.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping

MODE_VARIABLE = "AHAM_TEST_BWRAP_SUDO_HELPER"
HELPER_FLAG = "--sudo-namespace-helper"


@functools.lru_cache(maxsize=1)
def unprivileged_namespaces_work() -> bool:
    """Report whether Bubblewrap can build its namespaces without sudo here."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return False
    try:
        result = subprocess.run(
            [bwrap, "--die-with-parent", "--new-session", "--unshare-all", "--ro-bind", "/", "/", "--", "true"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def namespace_helper_args(
    env: Mapping[str, str] | None = None,
    *,
    probe: Callable[[], bool] = unprivileged_namespaces_work,
) -> list[str]:
    """Return the sandbox arguments selecting the namespace path for this host.

    Unset or empty: the ordinary unprivileged path. "1": always the sudo helper.
    "auto": the unprivileged path when the host allows it, otherwise the helper.
    """
    mode = (os.environ if env is None else env).get(MODE_VARIABLE, "")
    if mode == "":
        return []
    if mode == "1":
        return [HELPER_FLAG]
    if mode == "auto":
        return [] if probe() else [HELPER_FLAG]
    raise ValueError(f"{MODE_VARIABLE} must be unset, '1' or 'auto'")
