# SPDX-License-Identifier: MIT
import struct
import tarfile
import tempfile
import unittest
from pathlib import Path

from gravity_firmware.bluetooth import BluetoothFWCollection
from gravity_firmware.core import FWPackage
from gravity_firmware.open_firmware import OpenFirmwareCollection
from gravity_firmware.wifi import WiFiFWCollection


M4_WIFI_SOURCES = {
    "C-4388__s-C2/sakhalin.trx": b"wifi-firmware",
    "C-4388__s-C2/P-sakhalin-X0_M-WLMT_V-u__m-4.9.txt":
        b"boardrev =0x14\nmacaddr=00:00:00:00:00:00\n",
    "C-4388__s-C2/sakhalin-X0.clmb": b"wifi-regulatory",
    "C-4388__s-C2/sakhalin-X0.txcb": b"wifi-tx-power",
    "C-4388__s-C2/sakhalin.sig": b"wifi-signature",
}

M4_WIFI_OUTPUTS = {
    "brcm/brcmfmac4388c0-pcie.bin",
    "brcm/brcmfmac4388c0-pcie.txt",
    "brcm/brcmfmac4388c0-pcie.clm_blob",
    "brcm/brcmfmac4388c0-pcie.txcap_blob",
    "brcm/brcmfmac4388c0-pcie.sig",
}

M4_BT_SOURCES = {
    "BCM4388C2_23.5.224.1474_PCIE_macOS_Willamette_"
    "Sakhalin_CLPC_3ANT_OS_AMKOR_20251203.bin": b"bluetooth-firmware",
    "BCM4388C2_EVTv1_PCIE_macOS_Willamette_"
    "Sakhalin_CLPC_3ANT_OS_AMKOR_K_R_20240625.ptb": b"bluetooth-ptb",
    "BCM4388C2_23.5.224.1475_PCIE_macOS_Willamette_"
    "Sakhalin_CLPC_3ANT_OS_USI_20251203.bin": b"wrong-bluetooth-vendor",
    "BCM4388C2_EVTv1_PCIE_macOS_Willamette_"
    "Sakhalin_CLPC_3ANT_OS_USI_K_R_20240625.ptb": b"wrong-bluetooth-ptb",
}

M4_BT_OUTPUTS = {
    "brcm/brcmbt4388c2-apple,sakhalin-a.bin",
    "brcm/brcmbt4388c2-apple,sakhalin-a.ptb",
}


def read_newc(path):
    """Return regular-file data from the small newc archives we generate."""
    data = Path(path).read_bytes()
    offset = 0
    files = {}

    while True:
        offset = (offset + 3) & ~3
        if data[offset:offset + 6] != b"070701":
            raise AssertionError(f"bad newc magic at offset {offset}")
        fields = [
            int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16)
            for i in range(13)
        ]
        mode, size, namesize = fields[1], fields[6], fields[11]
        offset += 110
        name = data[offset:offset + namesize - 1].decode("ascii")
        offset += namesize
        offset = (offset + 3) & ~3
        body = data[offset:offset + size]
        offset += size

        if name == "TRAILER!!!":
            return files
        if mode & 0o170000 == 0o100000:
            files[name] = body


class M4FirmwareTest(unittest.TestCase):
    def test_source_tree_firmware_import_link(self):
        root = Path(__file__).resolve().parents[1]
        link = root / "src/gravity_firmware"
        self.assertTrue(link.is_symlink())
        self.assertEqual(root / "gravity_firmware", link.resolve())
        self.assertFalse((root / "src/asahi_firmware").is_symlink())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.wifi = self.root / "wifi"
        self.bluetooth = self.root / "bluetooth"
        self.open_firmware = self.root / "open"

        for name, data in M4_WIFI_SOURCES.items():
            path = self.wifi / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for name, data in M4_BT_SOURCES.items():
            path = self.bluetooth / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def tearDown(self):
        self.tmp.cleanup()

    def test_m4_archive_inventory_and_manifest(self):
        wifi = dict(WiFiFWCollection(str(self.wifi), machine="j773g").files())
        bluetooth = dict(BluetoothFWCollection(
            str(self.bluetooth), machine="j773g"
        ).files())
        open_fw = dict(OpenFirmwareCollection(
            machine="j773g", source_path=self.open_firmware
        ).files())

        self.assertEqual(M4_WIFI_OUTPUTS, set(wifi))
        self.assertEqual(M4_BT_OUTPUTS, set(bluetooth))
        self.assertEqual(set(), set(open_fw))

        selected = {
            name: (wifi | bluetooth | open_fw)[name]
            for name in M4_WIFI_OUTPUTS | M4_BT_OUTPUTS
        }
        out = self.root / "out"
        out.mkdir()
        with FWPackage(out) as package:
            package.add_files(sorted(selected.items()))

        expected = {
            f"vendorfw/{name}" for name in selected
        } | {"vendorfw/.vendorfw.manifest"}
        cpio_files = read_newc(out / "firmware.cpio")
        self.assertEqual(expected, set(cpio_files))

        manifest = cpio_files["vendorfw/.vendorfw.manifest"].decode("ascii")
        for name, fwfile in selected.items():
            self.assertEqual(fwfile.data, cpio_files[f"vendorfw/{name}"])
            self.assertIn(f"FILE {name} SHA256 {fwfile.sha}", manifest)

        with tarfile.open(out / "firmware.tar") as archive:
            self.assertEqual(set(selected), set(archive.getnames()))

    def test_m4_wifi_profile_is_required_for_generic_aliases(self):
        files = dict(WiFiFWCollection(str(self.wifi)).files())
        self.assertTrue(M4_WIFI_OUTPUTS.isdisjoint(files))

    def test_m4_wifi_profile_fails_on_incomplete_input(self):
        (self.wifi / "C-4388__s-C2/sakhalin.sig").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "sakhalin.sig"):
            dict(WiFiFWCollection(str(self.wifi), machine="j773g").files())

    def test_m4_bluetooth_profile_fails_on_incomplete_input(self):
        next(self.bluetooth.glob("*AMKOR*.ptb")).unlink()
        with self.assertRaisesRegex(FileNotFoundError, "sakhalin-a.ptb"):
            dict(BluetoothFWCollection(
                str(self.bluetooth), machine="j773g"
            ).files())


if __name__ == "__main__":
    unittest.main()
