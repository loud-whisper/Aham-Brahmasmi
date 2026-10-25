"""Prevent publication CI from gaining unreviewed execution or token privileges."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / '.github/workflows'


class PublicationCIPolicyTests(unittest.TestCase):
    def test_actions_have_immutable_official_commit_refs(self):
        for path in WORKFLOWS.glob('*.yml'):
            references = re.findall(r'^\s*uses:\s*(\S+)', path.read_text(), re.M)
            for reference in references:
                with self.subTest(workflow=path.name, action=reference):
                    self.assertRegex(reference, r'^actions/(checkout|setup-python)@[0-9a-f]{40}$')

    def test_jobs_have_read_only_tokens_and_checkout_does_not_persist_credentials(self):
        for path in WORKFLOWS.glob('*.yml'):
            text = path.read_text()
            with self.subTest(workflow=path.name):
                self.assertRegex(text, r'(?m)^permissions: \{\}$')
                self.assertNotRegex(text, r':\s*(write|write-all)\b')
                jobs = re.split(r'(?m)^  [a-z][a-z0-9-]*:\s*$', text.split('jobs:', 1)[1])[1:]
                self.assertTrue(jobs)
                for job in jobs:
                    self.assertRegex(job, r'(?m)^    permissions:\n      contents: read$')
                checkouts = re.findall(r'uses: actions/checkout@[^\n]+\n(.*?)(?=\n      -|\Z)', text, re.S)
                self.assertTrue(checkouts)
                for step in checkouts:
                    self.assertIn('persist-credentials: false', step)

    def test_untrusted_code_cannot_target_private_runners_or_privileged_triggers(self):
        for path in WORKFLOWS.glob('*.yml'):
            text = path.read_text()
            with self.subTest(workflow=path.name):
                self.assertNotIn('self-hosted', text)
                self.assertNotIn('pull_request_target', text)
                self.assertNotIn('workflow_run:', text)

    def test_manual_rehearsal_is_strict_and_upstream_network_is_opt_in(self):
        text = (WORKFLOWS / 'release-rehearsal.yml').read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertNotRegex(text, r'(?m)^  (push|pull_request|schedule):')
        self.assertIn('live_upstream:', text)
        self.assertIn('default: false', text)
        self.assertIn('sudo apt-get install -y bubblewrap', text)
        self.assertLess(text.index('sudo apt-get install -y bubblewrap'), text.index('Run unit tests'))
        self.assertIn('AHAM_TEST_BWRAP_SUDO_HELPER: "1"', text)
        self.assertRegex(text, r'if: .*inputs\.live_upstream')

    def test_dependency_updates_cover_actions_only_and_have_a_small_queue(self):
        text = (ROOT / '.github/dependabot.yml').read_text()
        ecosystems = re.findall(r'package-ecosystem:\s*"?([a-z-]+)', text)
        self.assertEqual(ecosystems, ['github-actions'])
        self.assertIn('open-pull-requests-limit: 1', text)
        self.assertIn('interval: "monthly"', text)


if __name__ == '__main__':
    unittest.main()
