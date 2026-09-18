#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in real IPSW test: scratch files/read-only mounts, no partition writes.

Run with the installer Python and PYTHONPATH=src:tests from the repository root:
  python3 tests/validate_m4_recovery_macos.py IPSW_OR_HTTPS_URL OUTPUT_DIRECTORY
The output directory must not already exist. No installer main() is invoked.
"""
import argparse
import hashlib
import os
from pathlib import Path
import plistlib
import subprocess
import tarfile
from types import SimpleNamespace

from gravity_firmware.core import FWPackage
from gravity_firmware.update import update_firmware
from stub import StubInstaller
from test_m4_firmware import read_newc, M4_WIFI_OUTPUTS, M4_BT_OUTPUTS
from recovery import file_checksums, QUALIFIED_IMAGES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipsw")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.ipsw if args.ipsw.startswith("https://") else str(Path(args.ipsw).resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = plistlib.loads(subprocess.check_output(["diskutil", "list", "-plist", "disk0"]))
    os.chdir(output)
    os.environ.pop("IPSW_BASE", None)
    sysinfo = SimpleNamespace(board_id=0x2A, chip_id=0x8132, device_class="j773gap")
    installer = StubInstaller(sysinfo, None, None)
    try:
        installer.load_ipsw(SimpleNamespace(version="26.6.2", url=source))
        assert installer.recovery_image is not None
        identity = installer.identity
        installer.pb_vgid = str(output / "preboot/test-volume-group")
        restore = Path(installer.pb_vgid) / installer.restore_bundle_path()
        restore.mkdir(parents=True)
        # collect_firmware reads the kernel from the restore bundle. Other FUD
        # objects are extracted by the real collector directly from the IPSW.
        for value in identity["Manifest"].values():
            member = value["Info"]["Path"]
            if member.startswith("kernelcache."):
                installer.extract(member, str(restore))
        recovery_root = output / "recovery-volume"
        installer.osi = SimpleNamespace(recovery=str(recovery_root), vgid="test-volume-group")
        target = recovery_root / "test-volume-group/usr/standalone/firmware/arm64eBaseSystem.dmg"
        target.parent.mkdir(parents=True)
        prepared = installer.recovery_image
        with prepared.path.open("rb") as stream:
            installer.stream_compress(stream, prepared.path.stat().st_size, str(target), crc=prepared.crc)
        expected = next(iter(QUALIFIED_IMAGES.values()))["decoded_sha256"]
        assert file_checksums(target)[0] == expected
        subprocess.run(["hdiutil", "verify", str(target)], check=True)
        (output / "vendorfw").mkdir()
        with FWPackage(str(output / "vendorfw")) as package:
            installer.collect_firmware(package)
        files = read_newc(output / "vendorfw/firmware.cpio")
        required = {"vendorfw/" + name for name in M4_WIFI_OUTPUTS | M4_BT_OUTPUTS}
        assert required <= files.keys(), required - files.keys()
        assert all(files[name] for name in required)
        assert not any("avd-fw" in name for name in files)
        with tarfile.open(output / "vendorfw/firmware.tar") as archive:
            for name in required:
                assert archive.extractfile(name.removeprefix("vendorfw/")).read() == files[name]
        with tarfile.open(output / "all_firmware.tar.gz") as archive:
            assert any(name.startswith("apple_bcmwlan_firmware/") for name in archive.getnames())
            assert any(name.startswith("firmware/bluetooth/") for name in archive.getnames())
        idata = output / "installer-data"
        idata.mkdir()
        (idata / "all_firmware.tar.gz").symlink_to(output / "all_firmware.tar.gz")
        for kernel in restore.glob("kernelcache.*"):
            (idata / kernel.name).symlink_to(kernel)
        update_firmware(idata, output / "rebuilt-vendorfw", machine="j773g")
        assert read_newc(output / "rebuilt-vendorfw/firmware.cpio") == files
        after = plistlib.loads(subprocess.check_output(["diskutil", "list", "-plist", "disk0"]))
        assert before == after, "Unexpected physical disk layout change"
        print("PASS: real AEA decode, DMG verification, APFS compression, read-only mount,")
        print("      firmware.cpio/tar contents, fwextract round-trip, unchanged disk0 layout")
        print("firmware.cpio SHA256:", hashlib.sha256((output / "vendorfw/firmware.cpio").read_bytes()).hexdigest())
    finally:
        if installer.recovery_image:
            installer.recovery_image.close()


if __name__ == "__main__":
    main()
