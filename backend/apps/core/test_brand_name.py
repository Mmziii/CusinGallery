"""
Brand spelling guard (Part 1).

The Persian brand name is «کازین گالری». The old spelling «کوزین گالری»
must never reappear in tracked sources (UI, templates, SMS/email copy,
docs). The forbidden literal is assembled at runtime so this file itself
never contains it.
"""
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

OLD_SPELLING = "کو" + "زین"  # assembled: this guard must not match itself
NEW_SPELLING = "کا" + "زین"


class BrandSpellingTests(SimpleTestCase):
    def test_old_persian_spelling_is_gone_from_tracked_sources(self):
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            ["git", "grep", "-I", "--name-only", OLD_SPELLING],
            cwd=root, capture_output=True, text=True,
        )
        self.assertEqual(
            result.stdout.strip(), "",
            f"old brand spelling found in: {result.stdout.strip()}",
        )

    def test_new_spelling_is_present_in_key_places(self):
        root = Path(__file__).resolve().parents[3]
        for rel in ("frontend/index.html", "backend/apps/notifications/services.py"):
            text = (root / rel).read_text(encoding="utf-8")
            self.assertIn(NEW_SPELLING, text, rel)
