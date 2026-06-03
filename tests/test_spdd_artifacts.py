from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPDD = ROOT / "spdd"


class SpddArtifactsTests(unittest.TestCase):
    def test_required_spdd_files_exist(self) -> None:
        required = [
            "README.md",
            "requirements.md",
            "analysis.md",
            "reasons-canvas.md",
            "test-scenarios.md",
            "verification.md",
            "conclusion.md",
            "prompts/001-initial-client.md",
            "prompts/002-mvc-blueprint-notifications.md",
            "prompts/003-spdd-compliance.md",
            "prompts/004-operational-hardening.md",
            "prompts/005-operator-workflow-polish.md",
            "prompts/006-fdo-branding-refresh.md",
        ]
        for relative_path in required:
            with self.subTest(relative_path=relative_path):
                self.assertTrue((SPDD / relative_path).is_file())

    def test_reasons_canvas_has_all_sections(self) -> None:
        text = (SPDD / "reasons-canvas.md").read_text(encoding="utf-8")
        for section in [
            "## R - Requirements",
            "## E - Entities",
            "## A - Approach",
            "## S - Structure",
            "## O - Operations",
            "## N - Norms",
            "## S - Safeguards",
        ]:
            with self.subTest(section=section):
                self.assertIn(section, text)

    def test_architecture_packages_exist(self) -> None:
        for package in ["blueprints", "controllers", "services", "views", "ui"]:
            with self.subTest(package=package):
                self.assertTrue((ROOT / "translazia_client" / package / "__init__.py").is_file())
