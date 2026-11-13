from __future__ import annotations

import unittest

from sandbox_helper import HELPER_FLAG, MODE_VARIABLE, namespace_helper_args


def probe_returning(result: bool):
    calls: list[bool] = []

    def probe() -> bool:
        calls.append(result)
        return result

    probe.calls = calls  # type: ignore[attr-defined]
    return probe


class SandboxHelperSelectionTests(unittest.TestCase):
    def test_unset_mode_uses_the_ordinary_unprivileged_path_without_probing(self) -> None:
        probe = probe_returning(False)
        self.assertEqual(namespace_helper_args({}, probe=probe), [])
        self.assertEqual(probe.calls, [])

    def test_forced_mode_uses_the_helper_without_probing(self) -> None:
        probe = probe_returning(True)
        self.assertEqual(namespace_helper_args({MODE_VARIABLE: "1"}, probe=probe), [HELPER_FLAG])
        self.assertEqual(probe.calls, [])

    def test_auto_mode_skips_the_helper_when_unprivileged_namespaces_work(self) -> None:
        self.assertEqual(namespace_helper_args({MODE_VARIABLE: "auto"}, probe=probe_returning(True)), [])

    def test_auto_mode_uses_the_helper_when_unprivileged_namespaces_are_blocked(self) -> None:
        self.assertEqual(
            namespace_helper_args({MODE_VARIABLE: "auto"}, probe=probe_returning(False)),
            [HELPER_FLAG],
        )

    def test_unknown_mode_is_rejected_instead_of_silently_changing_isolation(self) -> None:
        with self.assertRaises(ValueError):
            namespace_helper_args({MODE_VARIABLE: "yes"}, probe=probe_returning(True))


if __name__ == "__main__":
    unittest.main()
