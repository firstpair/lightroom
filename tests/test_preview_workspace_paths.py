import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "workspace_paths",
    Path(__file__).resolve().parents[1] / "scripts/preview_pipeline/workspace_paths.py",
)
paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.old = self.base / "former-workspace"
        self.new = self.base / "checkout/private-workspace"
        self.new.mkdir(parents=True)
        self.old.symlink_to(self.new, target_is_directory=True)
        self.file = self.new / "metadata.json"
        self.file.write_text('{"synthetic": true}\n')
        self.policy = paths.RelocatedWorkspace(
            self.old, self.new, paths.identity(self.old), paths.identity(self.new),
        )

    def test_historical_and_canonical_paths_select_same_unchanged_file(self):
        old_string = str(self.old / self.file.name)
        before = self.file.stat()
        self.assertEqual(self.policy.resolve(old_string), self.file)
        self.assertEqual(self.policy.resolve(self.file), self.file)
        self.assertEqual(str(self.old / self.file.name), old_string)
        self.assertEqual(self.file.stat(), before)

    def test_unrecorded_alias_is_not_accepted(self):
        other = self.base / "other-alias"
        other.symlink_to(self.new, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "OUTSIDE"):
            self.policy.resolve(other / self.file.name)

    def test_nested_symlink_refused_even_when_it_stays_inside(self):
        link = self.new / "alias.json"
        link.symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, "ADDITIONAL_SYMLINK"):
            self.policy.resolve(self.old / link.name)

    def test_directory_symlink_escape_refused(self):
        (self.new / "outside").symlink_to(self.base, target_is_directory=True)
        outside = self.base / "outside.json"
        outside.write_text("{}")
        with self.assertRaisesRegex(ValueError, "ADDITIONAL_SYMLINK"):
            self.policy.resolve(self.old / "outside/outside.json")

    def test_path_traversal_refused(self):
        with self.assertRaisesRegex(ValueError, "EXACT_ABSOLUTE"):
            self.policy.resolve(str(self.old) + "/../outside.json")

    def test_replaced_alias_refused_even_with_same_target(self):
        replacement = self.base / "replacement"
        replacement.symlink_to(self.new, target_is_directory=True)
        replacement.replace(self.old)
        with self.assertRaisesRegex(ValueError, "OLD_LINK_IDENTITY"):
            self.policy.resolve(self.old / self.file.name)

    def test_replaced_root_refused(self):
        self.new.rename(self.base / "retained-workspace")
        self.new.mkdir()
        with self.assertRaisesRegex(ValueError, "NEW_ROOT_IDENTITY"):
            self.policy.resolve(self.old / self.file.name)

    def test_missing_metadata_is_not_admitted(self):
        with self.assertRaises(FileNotFoundError):
            self.policy.resolve(self.old / "missing.json")


if __name__ == "__main__":
    unittest.main()
