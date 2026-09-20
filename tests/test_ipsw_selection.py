# SPDX-License-Identifier: MIT
import contextlib
import io
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import main


class IPSWSelectionTests(unittest.TestCase):
    def setUp(self):
        # Do not initialize the installer: that probes disks and macOS state.
        self.installer = main.InstallerMain.__new__(main.InstallerMain)
        self.installer.sysinfo = SimpleNamespace(
            sys_firmware="iBoot-18000.161.10", macos_ver="26.6.2",
            sfr_full_ver="26.6.2", chip_id=0x8132, device_class="j773gap")
        self.installer.device = main.DEVICES["j773gap"]
        self.installer.expert = False

    def choose(self, **minimums):
        ipsw = replace(main.IPSW_VERSIONS[0], **minimums)
        with patch.object(main, "IPSW_VERSIONS", [ipsw]), contextlib.redirect_stdout(io.StringIO()):
            return self.installer.choose_ipsw(["26.6.2"])

    def test_unrestricted_firmware_prefixes(self):
        for firmware in ("iBoot-18000.161.10", "mBoot-18000.161.10"):
            with self.subTest(firmware=firmware):
                self.installer.sysinfo.sys_firmware = firmware
                self.assertEqual(self.choose().version, "26.6.2")

    def test_real_firmware_minimum_is_enforced(self):
        self.assertEqual(self.choose(min_iboot="iBoot-18000.161.10").version, "26.6.2")
        with self.assertRaises(SystemExit):
            self.choose(min_iboot="iBoot-18000.161.11")

    def test_macos_minimum_is_enforced(self):
        self.installer.sysinfo.macos_ver = "26.4"
        with self.assertRaises(SystemExit):
            self.choose()

    def test_macos_265_selects_2662_firmware(self):
        self.installer.sysinfo.macos_ver = "26.5"
        self.assertEqual(self.choose().version, "26.6.2")

    def test_real_sfr_minimum_is_enforced(self):
        with self.assertRaises(SystemExit):
            self.choose(min_sfr="26.6.3")

    def test_zero_sfr_minimum_does_not_compare_prefixes(self):
        self.installer.sysinfo.sfr_full_ver = "example-26.6.2"
        self.assertEqual(self.choose().version, "26.6.2")


if __name__ == "__main__":
    unittest.main()
