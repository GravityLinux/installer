# SPDX-License-Identifier: MIT
"""Collect BCM4388 Wi-Fi and Bluetooth calibration from this Mac's factory data.

The factory IMG4 is parsed as data, without executing or disassembling firmware.
This validates the container and record structure, not the Apple signature.
"""
import hashlib
import json
import logging
import pathlib
import plistlib
import re
import subprocess

try:
    from . import asn1
except ImportError:
    import asn1
from .als import FACTORY_DIR
from .core import FWFile

log = logging.getLogger(__name__)
MAX_FACTORY_SIZE = 1024 * 1024
MAX_CALIBRATION_SIZE = 32768
RAW_METADATA = "apple/bluetooth-beamforming.json"
RAW_BLOB = "apple/bluetooth-beamforming.bin"
SEQ = asn1.Tag(asn1.Numbers.Sequence, asn1.Types.Constructed, 0)
INT = asn1.Tag(asn1.Numbers.Integer, asn1.Types.Primitive, 0)
STR = asn1.Tag(asn1.Numbers.IA5String, asn1.Types.Primitive, 0)
OCTETS = asn1.Tag(asn1.Numbers.OctetString, asn1.Types.Primitive, 0)


def items(data):
    decoder = asn1.Decoder()
    decoder.start(data)
    result = []
    while not decoder.eof():
        result.append(decoder.read())
    return result


def sequence(data):
    fields = items(data)
    if len(fields) != 1 or fields[0][0] != SEQ:
        raise ValueError("Expected one DER sequence")
    return items(fields[0][1])


def validate_blob(data):
    if not 4 <= len(data) <= MAX_CALIBRATION_SIZE or not data.startswith(b"BLOB"):
        raise ValueError("Invalid radio calibration")
    return data


def extract_record(data, record):
    if len(data) > MAX_FACTORY_SIZE:
        raise ValueError("Factory record exceeds size limit")
    outer = sequence(data)
    if len(outer) < 2 or outer[0] != (STR, "IMG4") or outer[1][0] != SEQ:
        raise ValueError("Expected factory IMG4 with IM4P payload")
    payload = items(outer[1][1])
    if (len(payload) != 4 or payload[0] != (STR, "IM4P") or
            payload[1] != (STR, "BWCl") or payload[2][0] != STR or
            payload[3][0] != OCTETS):
        raise ValueError("Expected uncompressed BWCl IM4P payload")
    records = sequence(payload[3][1])
    if not records or records[0] != (INT, int.from_bytes(b"BWCl", "little")):
        raise ValueError("Incorrect BWCl payload identifier")
    matches = []

    def visit(fields, depth=0):
        if depth > 8:
            raise ValueError("Factory record nesting exceeds limit")
        for tag, value in fields:
            if tag.typ != asn1.Types.Constructed:
                continue
            children = items(value)
            if tag == SEQ and children and children[0] == (INT, int.from_bytes(record, "little")):
                if len(children) != 3 or children[1][0] != STR or children[2][0] != OCTETS:
                    raise ValueError("Malformed calibration record")
                matches.append(validate_blob(children[2][1]))
            else:
                visit(children, depth + 1)

    visit(records)
    if len(matches) != 1:
        raise ValueError("Expected exactly one calibration record")
    return matches[0]


def extract_btbf(data):
    return extract_record(data, b"BTBF")


def radio_address(tree, property_name):
    """Use the same /chosen address as m1n1, before its DT byte reversal."""
    matches = []

    def visit(node):
        if isinstance(node, dict):
            if node.get("IORegistryEntryName") == "chosen":
                value = node.get(property_name)
                if value is not None:
                    matches.append(value)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(tree)
    if len(matches) != 1 or not isinstance(matches[0], bytes) or len(matches[0]) != 6:
        raise ValueError("Missing or ambiguous radio address in /chosen")
    if matches[0] in (bytes(6), b"\xff" * 6) or matches[0][0] & 1:
        raise ValueError("Invalid radio address")
    return matches[0].hex()


def bluetooth_address(tree):
    return radio_address(tree, "mac-address-bluetooth0")


class RadioCalibration:
    def __init__(self, address, data, provenance):
        if not isinstance(address, str) or not re.fullmatch(r"[0-9a-f]{12}", address):
            raise ValueError("Invalid radio calibration address")
        raw_address = bytes.fromhex(address)
        if raw_address in (bytes(6), b"\xff" * 6) or raw_address[0] & 1:
            raise ValueError("Invalid radio calibration address")
        self.address = address
        self.data = validate_blob(data)
        self.provenance = provenance

    @classmethod
    def collect(cls, factory_dir=FACTORY_DIR, tree=None):
        paths = sorted(pathlib.Path(factory_dir).glob("BWCl-sakhalin-4388-C2-*"))
        if not paths:
            log.warning("No J773g radio factory calibration found; radio calibration will be unavailable")
            return None
        if tree is None:
            registry = subprocess.run(["ioreg", "-p", "IODeviceTree", "-n", "chosen", "-r", "-a", "-l"],
                                      capture_output=True, check=True)
            tree = plistlib.loads(registry.stdout)
        address = radio_address(tree, cls.address_property)
        blobs = {}
        provenance = []
        for path in paths:
            if path.stat().st_size > MAX_FACTORY_SIZE:
                raise ValueError("Factory record exceeds size limit")
            raw = path.read_bytes()
            blob = extract_record(raw, cls.record)
            blobs[hashlib.sha256(blob).hexdigest()] = blob
            provenance.append({"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        if len(blobs) != 1:
            raise ValueError("Multiple different radio factory calibrations; refusing to choose")
        return cls(address, next(iter(blobs.values())), provenance)

    def files(self):
        name = self.filename.format(self.address)
        return [(name, FWFile(name, self.data))]

    def write_raw(self, directory):
        directory = pathlib.Path(directory)
        (directory / self.raw_blob).parent.mkdir(parents=True, exist_ok=True)
        (directory / self.raw_blob).write_bytes(self.data)
        metadata = {"version": 1, "address": self.address, "bytes": len(self.data),
                    "sha256": hashlib.sha256(self.data).hexdigest(), "factory_records": self.provenance}
        (directory / self.raw_metadata).write_text(json.dumps(metadata, indent=2) + "\n")

    @classmethod
    def from_archive(cls, directory):
        directory = pathlib.Path(directory)
        metadata_path = directory / cls.raw_metadata
        if not metadata_path.exists():
            log.warning("Saved firmware archive has no %s factory calibration", cls.record.decode())
            return None
        metadata = json.loads(metadata_path.read_text())
        blob_path = directory / cls.raw_blob
        if blob_path.stat().st_size > MAX_CALIBRATION_SIZE:
            raise ValueError("Saved radio calibration exceeds size limit")
        data = blob_path.read_bytes()
        if (metadata.get("version") != 1 or metadata.get("bytes") != len(data) or
                metadata.get("sha256") != hashlib.sha256(data).hexdigest()):
            raise ValueError("Saved radio calibration metadata mismatch")
        return cls(metadata.get("address"), data, metadata.get("factory_records", []))


class BluetoothCalibration(RadioCalibration):
    record = b"BTBF"
    address_property = "mac-address-bluetooth0"
    raw_metadata = RAW_METADATA
    raw_blob = RAW_BLOB
    filename = "brcm/brcmbt4388-{}-bf.bin"


class WiFiCalibration(RadioCalibration):
    """BCM4388 WLAN calibration from the same machine-local BWCl record."""
    record = b"WCAL"
    address_property = "mac-address-wifi0"
    raw_metadata = "apple/wifi-calibration.json"
    raw_blob = "apple/wifi-calibration.bin"
    filename = "brcm/brcmfmac4388-{}-cal.bin"
