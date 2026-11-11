# SPDX-License-Identifier: MIT
import tempfile
import unittest
from pathlib import Path

import m1n1


VARS = [
    "chosen.gravity,efi-system-partition=01234567-89ab-cdef-0123-456789abcdef",
    "chainload=01234567-89ab-cdef-0123-456789abcdef;m1n1/boot.bin",
]


class BootObjectVariableTests(unittest.TestCase):
    def round_trip(self, stage1):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "m1n1.bin"
            dest = Path(tmp) / "boot.bin"
            src.write_bytes(stage1)
            m1n1.build(src, dest, VARS)
            self.assertEqual(0, dest.stat().st_size % (64 * 1024))
            return m1n1.extract_vars(dest)

    def test_plain_stage1(self):
        self.assertEqual(VARS, self.round_trip(b"code" + b"STACKBOT"))

    def test_stage1_with_boot_logo(self):
        logo = m1n1.LOGO_MAGIC + bytes([0, 0, 0, 255]) * (m1n1.LOGO_SIZE // 4)
        self.assertEqual(VARS, self.round_trip(b"code" + b"STACKBOT" + logo))


if __name__ == "__main__":
    unittest.main()
