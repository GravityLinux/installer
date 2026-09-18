# SPDX-License-Identifier: MIT
"""Decode the qualified restore image before touching the target disk.

The AEA key below is Apple-published release material, not a device secret.
It was resolved with ipsw v3.1.722 from the archive's public FCS metadata:
https://wkms-public.apple.com/fcs-keys/iH707G4WnpWgYOxDeMRHQUtlbIsfVaeIA86lDBYsT2U=
Both encrypted and decoded bytes are pinned; new restore builds must be
qualified explicitly rather than reusing a key based only on a version string.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zlib


QUALIFIED_IMAGES = {
    ("26.6.2", "022-22048-093.dmg.aea"): {
        "encrypted_sha256": "4e91f4949f0614de01f44434bce2a5a45b0e0a92ca0e3b06cd55c229752a9754",
        "decoded_sha256": "eeda386b1fb66a313cadef26e3e7ee06643d4d5ea8b3330a411a118ac7d14ed3",
        "key": "base64:WYNVRNc/IXaQQi1cN2hGFNsELwlDuMHjSRi97lyIQJo=",
    },
}


def file_checksums(path):
    digest = hashlib.sha256()
    crc = 0
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            crc = zlib.crc32(block, crc)
    return digest.hexdigest(), crc


@contextmanager
def mounted_recovery(image):
    with tempfile.TemporaryDirectory(prefix="gravity-recovery-mount-") as mount:
        subprocess.run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse",
                        "-mountpoint", mount, str(image)], check=True)
        try:
            yield Path(mount)
        finally:
            subprocess.run(["/usr/bin/hdiutil", "detach", mount], check=True)


class RecoveryImage:
    def __init__(self, package, member, version):
        profile = QUALIFIED_IMAGES.get((version, member))
        if profile is None:
            raise ValueError(f"Unqualified AEA recovery image: {version}: {member}")
        if not os.access("/usr/bin/aea", os.X_OK):
            raise RuntimeError("This restore image requires macOS /usr/bin/aea")
        # Staging holds the ~1.1 GB archive and ~1.5 GB decoded DMG.
        if shutil.disk_usage(tempfile.gettempdir()).free < 4 * 1024**3:
            raise RuntimeError("Need at least 4 GiB temporary space to decode recovery")
        self.temporary = tempfile.TemporaryDirectory(prefix="gravity-recovery-")
        try:
            root = Path(self.temporary.name)
            encrypted = root / "BaseSystem.dmg.aea"
            self.path = root / "BaseSystem.dmg"
            with package.open(member) as source, encrypted.open("xb") as out:
                shutil.copyfileobj(source, out, length=1024 * 1024)
            if file_checksums(encrypted)[0] != profile["encrypted_sha256"]:
                raise ValueError("AEA recovery archive SHA-256 mismatch")
            # A key file avoids exposing key data in process arguments/logs.
            key_file = root / "aea.key"
            key_file.write_text(profile["key"])
            key_file.chmod(0o600)
            subprocess.run(["/usr/bin/aea", "decrypt", "-i", str(encrypted),
                            "-o", str(self.path), "-key", str(key_file)], check=True)
            digest, self.crc = file_checksums(self.path)
            if digest != profile["decoded_sha256"]:
                raise ValueError("Decoded recovery DMG SHA-256 mismatch")
            subprocess.run(["/usr/bin/hdiutil", "verify", str(self.path)], check=True)
            encrypted.unlink()
            key_file.unlink()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.temporary.cleanup()
