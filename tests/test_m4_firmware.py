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


J713_SKUS = ("ID", "X0", "X2", "X3")

J713_WIFI_SOURCES = {
    "C-4388__s-C2/garden.trx": b"wifi-firmware",
    "C-4388__s-C2/garden.sig": b"wifi-signature",
    **{f"C-4388__s-C2/garden-{sku}.trx": b"wifi-firmware" for sku in J713_SKUS},
    **{f"C-4388__s-C2/garden-{sku}.clmb": b"wifi-regulatory" for sku in J713_SKUS},
    **{f"C-4388__s-C2/garden-{sku}.txcb": b"wifi-tx-power" for sku in J713_SKUS},
    **{f"C-4388__s-C2/P-garden-{sku}_M-WLMT_V-{vendor}__m-4.9.txt":
           f"boardrev =0x14\nvendor={vendor}\n".encode()
       for sku in J713_SKUS for vendor in "au"},
    # Another board and an unlisted variant must not leak into the profile.
    "C-4388__s-C2/sakhalin.trx": b"other-board",
    "C-4388__s-C2/garden.clmb": b"board-level-regulatory",
}

J713_WIFI_OUTPUTS = {
    "brcm/brcmfmac4388c0-pcie.apple,garden.bin",
    "brcm/brcmfmac4388c0-pcie.apple,garden.sig",
    *(f"brcm/brcmfmac4388c0-pcie.apple,garden-{sku}.{ext}"
      for sku in J713_SKUS for ext in ("bin", "clm_blob", "txcap_blob")),
    *(f"brcm/brcmfmac4388c0-pcie.apple,garden-WLMT-{vendor}-4.9-{sku}.txt"
      for sku in J713_SKUS for vendor in "au"),
}

J713_BT_SOURCES = {
    "BCM4388C2_23.5.224.1476_PCIE_macOS_Willamette_"
    "Garden_CLPC_OS_AMKOR_20251203.bin": b"bluetooth-firmware-a",
    "BCM4388C2_P1v1_PCIE_macOS_Willamette_"
    "Garden_CLPC_OS_AMKOR_K_R_20240524.ptb": b"bluetooth-ptb",
    "BCM4388C2_23.5.224.1477_PCIE_macOS_Willamette_"
    "Garden_CLPC_OS_USI_20251203.bin": b"bluetooth-firmware-u",
    "BCM4388C2_P1v1_PCIE_macOS_Willamette_"
    "Garden_CLPC_OS_USI_K_R_20240524.ptb": b"bluetooth-ptb",
}

J713_BT_OUTPUTS = {
    "brcm/brcmbt4388c2-apple,garden-a.bin",
    "brcm/brcmbt4388c2-apple,garden-a.ptb",
    "brcm/brcmbt4388c2-apple,garden-u.bin",
    "brcm/brcmbt4388c2-apple,garden-u.ptb",
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


class J713FirmwareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.wifi = self.root / "wifi"
        self.bluetooth = self.root / "bluetooth"

        for name, data in J713_WIFI_SOURCES.items():
            path = self.wifi / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        # The Recovery image carries every board's Bluetooth firmware.
        for name, data in (M4_BT_SOURCES | J713_BT_SOURCES).items():
            path = self.bluetooth / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def tearDown(self):
        self.tmp.cleanup()

    def test_j713_archive_inventory(self):
        wifi = dict(WiFiFWCollection(str(self.wifi), machine="j713").files())
        bluetooth = dict(BluetoothFWCollection(
            str(self.bluetooth), machine="j713"
        ).files())
        open_fw = dict(OpenFirmwareCollection(machine="j713").files())

        self.assertEqual(J713_WIFI_OUTPUTS, set(wifi))
        self.assertEqual(J713_BT_OUTPUTS, set(bluetooth))
        self.assertEqual(set(), set(open_fw))
        self.assertEqual(
            b"boardrev=0x14\nvendor=u\n",
            wifi["brcm/brcmfmac4388c0-pcie.apple,garden-WLMT-u-4.9-X0.txt"].data)
        self.assertEqual(
            b"bluetooth-firmware-u",
            bluetooth["brcm/brcmbt4388c2-apple,garden-u.bin"].data)

        out = self.root / "out"
        out.mkdir()
        with FWPackage(out) as package:
            package.add_files(sorted((wifi | bluetooth).items()))

        cpio_files = read_newc(out / "firmware.cpio")
        manifest = cpio_files["vendorfw/.vendorfw.manifest"].decode("ascii")
        names = {line.split()[1] for line in manifest.splitlines()}
        self.assertEqual(J713_WIFI_OUTPUTS | J713_BT_OUTPUTS, names)

    def test_j713_and_j773g_profiles_are_disjoint(self):
        self.assertTrue(J713_WIFI_OUTPUTS.isdisjoint(M4_WIFI_OUTPUTS))
        self.assertTrue(J713_BT_OUTPUTS.isdisjoint(M4_BT_OUTPUTS))
        with self.assertRaisesRegex(FileNotFoundError, "sakhalin"):
            dict(WiFiFWCollection(str(self.wifi), machine="j773g").files())

    def test_j713_wifi_profile_fails_on_incomplete_input(self):
        (self.wifi / "C-4388__s-C2/garden-X3.txcb").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "garden-X3.txcb"):
            dict(WiFiFWCollection(str(self.wifi), machine="j713").files())

    def test_j713_bluetooth_profile_fails_on_incomplete_input(self):
        next(self.bluetooth.glob("*Garden*USI*.bin")).unlink()
        with self.assertRaisesRegex(FileNotFoundError, "garden-u.bin"):
            dict(BluetoothFWCollection(
                str(self.bluetooth), machine="j713"
            ).files())

    def test_unknown_machine_profile_is_rejected(self):
        for collection, source in ((WiFiFWCollection, self.wifi),
                                   (BluetoothFWCollection, self.bluetooth)):
            with self.assertRaisesRegex(ValueError, "j715"):
                collection(str(source), machine="j715")
        with self.assertRaisesRegex(ValueError, "j715"):
            OpenFirmwareCollection(machine="j715")


if __name__ == "__main__":
    unittest.main()
