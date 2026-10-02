from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_start_here_keeps_one_instruction_before_technical_setup(self) -> None:
        text = (ROOT / "START_HERE.md").read_text(encoding="utf-8")
        user_instruction = "Read `START_HERE.md` and set this up for me."
        assistant_heading = "## Instructions for the assistant"
        self.assertIn(user_instruction, text)
        self.assertIn(assistant_heading, text)
        self.assertLess(text.index(user_instruction), text.index(assistant_heading))
        opening = text[: text.index(assistant_heading)]
        self.assertIn("You do not need to know Git, Python, command lines", opening)

    def test_first_run_defines_project_specific_words_before_assistant_section(self) -> None:
        text = (ROOT / "START_HERE.md").read_text(encoding="utf-8")
        opening = text[: text.index("## Instructions for the assistant")]
        for term in (
            "**Brain**",
            "**framework**",
            "**private workspace**",
            "**runtime**",
            "**checkpoint**",
            "**wrap up**",
            "**semantic memory**",
            "**Git**",
            "**skill**",
        ):
            self.assertIn(term, opening)

    def test_readme_points_to_plain_language_help_and_architecture(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("`START_HERE.md`", text)
        self.assertIn("`docs/TROUBLESHOOTING.md`", text)
        self.assertIn("`docs/ARCHITECTURE.md`", text)

    def test_funding_links_use_supported_keys_and_match_readme(self) -> None:
        # GitHub ignores unknown FUNDING.yml keys silently, so a typo would hide the Sponsor button.
        entries = {}
        for line in (ROOT / ".github" / "FUNDING.yml").read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                key, value = line.split(":", 1)
                entries[key.strip()] = value.strip()
        self.assertEqual(entries, {"github": "loud-whisper", "ko_fi": "vm1700"})
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/sponsors/loud-whisper", readme)
        self.assertIn("https://ko-fi.com/vm1700", readme)

    def test_readme_overview_image_exists(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("](docs/assets/overview.png)", readme)
        self.assertTrue((ROOT / "docs" / "assets" / "overview.png").is_file())

    def test_architecture_repeats_user_ownership_principle(self) -> None:
        text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIn("Everything important belongs to the user", text)
        self.assertIn("External-source safety", text)
        self.assertIn("Optional memory and history", text)


if __name__ == "__main__":
    unittest.main()
