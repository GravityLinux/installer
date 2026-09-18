# SPDX-License-Identifier: MIT
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

import recovery


class FakePackage:
    def __init__(self, data):
        self.data = data

    def open(self, member):
        return io.BytesIO(self.data)


class RecoveryTests(unittest.TestCase):
    def test_unknown_archive_rejected_before_decode(self):
        with self.assertRaisesRegex(ValueError, "Unqualified"):
            recovery.RecoveryImage(FakePackage(b""), "other.dmg.aea", "26.6.2")

    def test_hash_and_decode_failures_cleanup(self):
        encrypted, decoded = b"AEA1 fixture", b"decoded fixture"
        profile = {"encrypted_sha256": hashlib.sha256(encrypted).hexdigest(),
                   "decoded_sha256": hashlib.sha256(decoded).hexdigest(), "key": "base64:TEST"}
        for case in ("valid", "bad_archive", "bad_output", "decoder_failure"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                def run(command, check):
                    if command[0] == "/usr/bin/aea":
                        self.assertEqual(Path(command[-1]).stat().st_mode & 0o777, 0o600)
                        if case == "decoder_failure":
                            raise recovery.subprocess.CalledProcessError(1, command)
                        Path(command[command.index("-o") + 1]).write_bytes(
                            b"bad output" if case == "bad_output" else decoded)
                with patch.dict(recovery.QUALIFIED_IMAGES, {("test", "image.aea"): profile}), \
                     patch.object(recovery.os, "access", return_value=True), \
                     patch.object(recovery.tempfile, "tempdir", temp), \
                     patch.object(recovery.shutil, "disk_usage", return_value=type("Space", (), {"free": 8 * 1024**3})()), \
                     patch.object(recovery.subprocess, "run", side_effect=run) as commands:
                    package = FakePackage(b"corrupt" if case == "bad_archive" else encrypted)
                    if case == "valid":
                        image = recovery.RecoveryImage(package, "image.aea", "test")
                        self.assertEqual(image.path.read_bytes(), decoded)
                        self.assertEqual(image.crc, zlib.crc32(decoded))
                        self.assertEqual(commands.call_count, 2)
                        image.close()
                    else:
                        with self.assertRaises((ValueError, recovery.subprocess.CalledProcessError)):
                            recovery.RecoveryImage(package, "image.aea", "test")
                        if case == "bad_archive":
                            commands.assert_not_called()
                    self.assertEqual(list(Path(temp).iterdir()), [])

    def test_detach_on_consumer_failure(self):
        with patch.object(recovery.subprocess, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "consumer"):
                with recovery.mounted_recovery("test.dmg"):
                    raise RuntimeError("consumer")
            self.assertEqual(command.call_args_list[-1].args[0][1], "detach")


if __name__ == "__main__":
    unittest.main()
