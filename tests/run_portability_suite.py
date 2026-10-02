#!/usr/bin/env python3
"""Run the cross-platform core suite without Linux-only live rehearsal modules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


TESTS = Path(__file__).resolve().parent
LINUX_ONLY_MODULES = {
    "test_astra_m6_live_evidence_emission.py",
    "test_m5_live_rehearsal_isolation.py",
    "test_m5_rehearsal_sandbox.py",
    "test_runtime_negative_path_rehearsal.py",
    "test_runtime_switch_handoff_containment.py",
    "test_runtime_switch_recovery.py",
}


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name in LINUX_ONLY_MODULES:
            continue
        suite.addTests(loader.discover(str(TESTS), pattern=path.name, top_level_dir=str(TESTS)))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
