from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path


TESTS = Path(__file__).resolve().parent
PORTABILITY_RUNNER = TESTS / "run_portability_suite.py"


def load_portability_runner():
    spec = importlib.util.spec_from_file_location("aham_run_portability_suite", PORTABILITY_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load portability runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def linux_only_test_modules() -> set[str]:
    modules: set[str] = set()
    for path in sorted(TESTS.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            decorators = getattr(node, "decorator_list", ())
            for decorator in decorators:
                rendered = ast.unparse(decorator)
                if "skipUnless" in rendered and "linux" in rendered.lower():
                    modules.add(path.name)
                    break
            if path.name in modules:
                break
    return modules


class R5PortabilitySuiteScopeTests(unittest.TestCase):
    def test_all_explicit_linux_only_modules_are_excluded_from_cross_platform_suite(self) -> None:
        runner = load_portability_runner()
        linux_only = linux_only_test_modules()
        self.assertTrue(linux_only, "expected at least one explicit Linux-only test module")
        missing = linux_only - set(runner.LINUX_ONLY_MODULES)
        self.assertFalse(
            missing,
            "cross-platform portability suite includes explicit Linux-only modules: "
            + ", ".join(sorted(missing)),
        )


if __name__ == "__main__":
    unittest.main()
