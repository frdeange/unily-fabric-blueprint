import tempfile
import unittest
from pathlib import Path

from tools.check_repository import ALLOWED_DIRECTORIES, EXCLUDED, EXPECTED_ITEMS, GUID_EXEMPT_FILES, check_fabric_scope


class LayoutTests(unittest.TestCase):
    def make_items(self, root):
        for item in EXPECTED_ITEMS:
            folder = root / "fabric" / item
            folder.mkdir(parents=True)
            (folder / ".platform").write_text("{}", encoding="utf-8")

    def test_nested_scope_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_items(root)
            check_fabric_scope(root)

    def test_unapproved_item_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_items(root)
            extra = root / "fabric" / "support" / "models" / "Unexpected.SemanticModel"
            extra.mkdir(parents=True)
            (extra / ".platform").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "scope"):
                check_fabric_scope(root)

    def test_loose_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_items(root)
            (root / "fabric" / "unexpected.txt").write_text("test", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside"):
                check_fabric_scope(root)

    def test_missing_item_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "scope"):
                check_fabric_scope(Path(directory))


class AppScopeTests(unittest.TestCase):
    def test_apps_are_allowed_and_build_artifacts_excluded(self):
        self.assertIn("apps", ALLOWED_DIRECTORIES)
        self.assertTrue({"node_modules", "dist"} <= EXCLUDED)

    def test_only_the_telemetry_id_file_is_guid_exempt(self):
        self.assertEqual(
            GUID_EXEMPT_FILES,
            {Path("apps") / "usage-explorer" / "rayfin" / ".project.json"},
        )


if __name__ == "__main__":
    unittest.main()
