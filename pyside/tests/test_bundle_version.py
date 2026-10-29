"""Packaging regressions, runnable without Qt, PyInstaller or native binaries."""

import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
bundle_version = runpy.run_path(str(ROOT / "scripts" / "bundle_version.py"))[
    "bundle_version"
]


class BundleVersionTests(unittest.TestCase):
    def test_release_tag_overrides_older_changelog(self):
        self.assertEqual(
            bundle_version(
                ROOT,
                {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v26.10.30.2"},
            ),
            "26.10.30.2",
        )

    def test_local_build_uses_latest_release_not_unreleased(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CHANGELOG.md").write_text(
                "## [Unreleased]\n\n## [v26.10.29.1] - 2026-10-29\n"
                "## [v26.10.28.1] - 2026-10-28\n"
            )
            self.assertEqual(bundle_version(root, {}), "26.10.29.1")
            self.assertEqual(
                bundle_version(root, {"GITHUB_REF_TYPE": "branch"}), "26.10.29.1"
            )

    def test_invalid_release_tags_fail_instead_of_falling_back(self):
        for tag in ("", "vbanana", "26.10.29.1", "v26.10.29.0", "v26.02.30.1"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                bundle_version(ROOT, {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": tag})

    def test_missing_changelog_version_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CHANGELOG.md").write_text("## [Unreleased]\n")
            with self.assertRaises(ValueError):
                bundle_version(root, {})

    def test_actual_spec_passes_both_bundle_fields(self):
        # Execute the real spec with inert packaging objects. Nothing is built,
        # no models are imported, and no native executable is run.
        class Analysis:
            def __init__(self, *args, **kwargs):
                for name in (
                    "pure",
                    "zipped_data",
                    "scripts",
                    "binaries",
                    "datas",
                    "zipfiles",
                ):
                    setattr(self, name, [])

        hooks = types.ModuleType("PyInstaller.utils.hooks")
        hooks.collect_all = lambda name: ([], [], [])
        bundle_calls = []

        def inert(*args, **kwargs):
            return None

        globals_ = {
            "SPECPATH": str(ROOT / "pyside"),
            "Analysis": Analysis,
            "PYZ": inert,
            "EXE": inert,
            "COLLECT": inert,
            "BUNDLE": lambda *args, **kwargs: bundle_calls.append(kwargs),
        }
        with (
            patch.dict(sys.modules, {"PyInstaller.utils.hooks": hooks}),
            patch.object(sys, "platform", "darwin"),
            patch.dict(
                "os.environ",
                {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v26.10.30.2"},
            ),
        ):
            runpy.run_path(str(ROOT / "pyside" / "pycapslap.spec"), globals_)
        self.assertEqual(len(bundle_calls), 1)
        self.assertEqual(bundle_calls[0]["version"], "26.10.30.2")
        plist = bundle_calls[0]["info_plist"]
        self.assertEqual(plist["CFBundleShortVersionString"], "26.10.30.2")
        self.assertEqual(plist["CFBundleVersion"], "26.10.30.2")


if __name__ == "__main__":
    unittest.main()
