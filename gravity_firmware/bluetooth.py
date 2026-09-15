# SPDX-License-Identifier: MIT
import logging, os, os.path, re, sys
from collections import namedtuple, defaultdict

from .core import FWFile

log = logging.getLogger("gravity_firmware.bluetooth")

BluetoothChip = namedtuple(
    "BluetoothChip", ("chip", "stepping", "board_type", "vendor")
)

# 13.5 is missing PTBs for these. 4388B0 probably never shipped to end users here.
INCOMPLETE_CHIPS = set([
    ('4388', 'b0', 'apple,tokara'),
    ('4388', 'b0', 'apple,amami'),
])

MACHINE_OUTPUTS = {
    "j773g": (
        "brcm/brcmbt4388c2-apple,sakhalin-a.bin",
        "brcm/brcmbt4388c2-apple,sakhalin-a.ptb",
    ),
}

class BluetoothFWCollection(object):
    VENDORMAP = {
        "AMKOR": "a",
        "MUR": "m",
        "USI": "u",
        "GEN": None,
    }
    STRIP_SUFFIXES = [
        "ES2"
    ]

    def __init__(self, source_path, machine=None):
        if machine is not None and machine not in MACHINE_OUTPUTS:
            raise ValueError(f"Unknown Bluetooth firmware machine profile: {machine}")
        self.machine = machine
        self.fwfiles = defaultdict(lambda: [None, None])
        self.load(source_path)

    def load(self, source_path):
        for fname in os.listdir(source_path):
            root, ext = os.path.splitext(fname)

            # index for bin and ptb inside self.fwfiles
            if ext == ".bin":
                idx = 0
            elif ext == ".ptb":
                idx = 1
            else:
                # skip firmware for older (UART) chips
                continue

            # skip T2 _DEV firmware
            if "_DEV" in root:
                continue

            chip = self.parse_fname(root)
            if chip is None:
                continue

            if self.fwfiles[chip][idx] is not None:
                log.warning(f"duplicate entry for {chip}: {self.fwfiles[chip][idx].name} and now {fname}")
                continue

            path = os.path.join(source_path, fname)
            with open(path, "rb") as f:
                data = f.read()

            self.fwfiles[chip][idx] = FWFile(fname, data)

    def parse_fname(self, fname):
        fname = fname.split("_")

        # Universal recovery images also contain non-Broadcom firmware.
        if not fname[0].lower().startswith("bcm"):
            return None

        match = re.fullmatch("bcm(43[0-9]{2})([a-z][0-9])", fname[0].lower())
        if not match:
            log.warning(f"Unexpected firmware file: {fname}")
            return None
        chip, stepping = match.groups()

        # board type is either preceded by PCIE_macOS or by PCIE
        try:
            pcie_offset = fname.index("PCIE")
        except:
            log.warning(f"Can't find board type in {fname}")
            return None

        bt_offset = pcie_offset + 1
        if fname[bt_offset] == "macOS":
            bt_offset += 1

        # 4388 has this extra prefix, meh
        if fname[bt_offset] == "Willamette":
            bt_offset += 1

        board_type = fname[bt_offset]

        for i in self.STRIP_SUFFIXES:
            board_type = board_type.rstrip(i)
        board_type = "apple," + board_type.lower()

        # make sure we can identify exactly one vendor
        otp_values = set()
        for vendor, otp_value in self.VENDORMAP.items():
            if vendor in fname:
                otp_values.add(otp_value)
        if len(otp_values) != 1:
            log.warning(f"Unable to determine vendor ({otp_values}) in {fname}")
            return None
        vendor = otp_values.pop()

        return BluetoothChip(
            chip=chip, stepping=stepping, board_type=board_type, vendor=vendor
        )

    def files(self):
        files = {}
        for chip, (bin, ptb) in self.fwfiles.items():
            fname_base = f"brcm/brcmbt{chip.chip}{chip.stepping}-{chip.board_type}"
            if chip.vendor is not None:
                fname_base += f"-{chip.vendor}"

            if bin is None:
                log.warning(f"no bin for {chip}")
            else:
                files[fname_base + ".bin"] = bin

            if ptb is None:
                if (chip.chip, chip.stepping, chip.board_type) not in INCOMPLETE_CHIPS:
                    log.warning(f"no ptb for {chip}")
                continue
            else:
                files[fname_base + ".ptb"] = ptb

        if self.machine is None:
            yield from files.items()
            return

        for name in MACHINE_OUTPUTS[self.machine]:
            try:
                yield name, files[name]
            except KeyError:
                raise FileNotFoundError(
                    f"Missing Bluetooth firmware for {self.machine}: {name}"
                ) from None


if __name__ == "__main__":
    col = BluetoothFWCollection(sys.argv[1])

    if len(sys.argv) > 2:
        from . import FWPackage

        pkg = FWPackage(sys.argv[2])
        pkg.add_files(sorted(col.files()))
        pkg.close()

        for i in pkg.manifest:
            print(i)
    else:
        for name, fwfile in col.files():
            print(name, f"{fwfile.name} ({len(fwfile.data)} bytes)")
