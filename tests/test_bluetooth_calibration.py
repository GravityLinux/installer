# SPDX-License-Identifier: MIT
"""Synthetic data only: no machine calibration or Apple firmware fixtures."""
import json
import tempfile
import unittest
from pathlib import Path
from gravity_firmware import asn1
from gravity_firmware.bluetooth_calibration import (
    BluetoothCalibration, RAW_BLOB, RAW_METADATA, bluetooth_address, extract_btbf,
)
from gravity_firmware.core import FWPackage

ADDRESS = "021122334455"
BLOB = b"BLOB" + bytes(range(256))
TREE = [{"IORegistryEntryName": "chosen", "mac-address-bluetooth0": bytes.fromhex(ADDRESS)}]


def factory(blobs=(BLOB,)):
    payload = asn1.Encoder()
    payload.start()
    payload.enter(asn1.Numbers.Sequence)
    payload.write(int.from_bytes(b"BWCl", "little"))
    for blob in blobs:
        payload.enter(asn1.Numbers.Sequence)
        payload.write(int.from_bytes(b"BTBF", "little"))
        payload.write("synthetic", asn1.Numbers.IA5String)
        payload.write(blob, asn1.Numbers.OctetString)
        payload.leave()
    payload.leave()
    container = asn1.Encoder()
    container.start()
    container.enter(asn1.Numbers.Sequence)
    container.write("IMG4", asn1.Numbers.IA5String)
    container.enter(asn1.Numbers.Sequence)
    for value in ("IM4P", "BWCl", "synthetic"):
        container.write(value, asn1.Numbers.IA5String)
    container.write(payload.output(), asn1.Numbers.OctetString)
    container.leave()
    container.leave()
    return container.output()


class CalibrationTests(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(extract_btbf(factory()), BLOB)

    def test_reject_invalid_records(self):
        for raw in (factory(()), factory((BLOB, BLOB)), factory((b"bad!",)),
                    factory((b"BLOB" + bytes(32768),)), factory()[:-1],
                    factory() + b"\x00", b"x" * (1024 * 1024 + 1)):
            with self.subTest(length=len(raw)):
                with self.assertRaises((ValueError, asn1.Error)):
                    extract_btbf(raw)

    def test_address(self):
        self.assertEqual(bluetooth_address(TREE), ADDRESS)
        for address in (bytes(6), b"\xff" * 6, b"\x01" + bytes(5), b"short"):
            with self.assertRaises(ValueError):
                bluetooth_address([{"IORegistryEntryName": "chosen", "mac-address-bluetooth0": address}])
        with self.assertRaises(ValueError):
            bluetooth_address(TREE + TREE)

    def test_collect_conflicting_factory_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(BluetoothCalibration.collect(root, TREE))
            (root / "BWCl-sakhalin-4388-C2-one").write_bytes(factory())
            (root / "BWCl-sakhalin-4388-C2-two").write_bytes(factory())
            calibration = BluetoothCalibration.collect(root, TREE)
            self.assertEqual(calibration.data, BLOB)
            self.assertEqual(len(calibration.provenance), 2)
            (root / "BWCl-sakhalin-4388-C2-two").write_bytes(factory((b"BLOBdifferent",)))
            with self.assertRaises(ValueError):
                BluetoothCalibration.collect(root, TREE)

    def test_archive_and_esp_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calibration = BluetoothCalibration(ADDRESS, BLOB, [])
            calibration.write_raw(root)
            restored = BluetoothCalibration.from_archive(root)
            with FWPackage(root) as package:
                package.add_files(restored.files())
            self.assertEqual((root / f"u-boot/brcm/brcmbt4388-{ADDRESS}-bf.bin").read_bytes(), BLOB)
            self.assertIn(f"brcmbt4388-{ADDRESS}-bf.bin", (root / "manifest.txt").read_text())
            (root / RAW_BLOB).write_bytes(b"BLOBwrong")
            with self.assertRaises(ValueError):
                BluetoothCalibration.from_archive(root)
            calibration.write_raw(root)
            metadata = json.loads((root / RAW_METADATA).read_text())
            metadata["address"] = "../bad-address"
            (root / RAW_METADATA).write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                BluetoothCalibration.from_archive(root)


if __name__ == "__main__":
    unittest.main()
