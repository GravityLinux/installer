# SPDX-License-Identifier: MIT
import unittest

from stub import StubInstaller


class RestoreBundleTests(unittest.TestCase):
    def make_installer(self, version, bless2):
        installer = StubInstaller.__new__(StubInstaller)
        installer.install_version = version
        installer.bootcaches = {"bless2": bless2}
        return installer

    def test_2662_missing_key(self):
        installer = self.make_installer("26.6.2", {"Version": 1, "BootObjects": {}})
        self.assertEqual(installer.restore_bundle_path(), "restore")

    def test_explicit_path_preserved(self):
        for version in ("12.3", "26.6.2"):
            with self.subTest(version=version):
                installer = self.make_installer(version, {"RestoreBundlePath": "./custom-restore"})
                self.assertEqual(installer.restore_bundle_path(), "./custom-restore")

    def test_unknown_layout_not_guessed(self):
        with self.assertRaisesRegex(ValueError, "Missing RestoreBundlePath"):
            self.make_installer("27.0", {}).restore_bundle_path()


if __name__ == "__main__":
    unittest.main()
