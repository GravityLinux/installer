# SPDX-License-Identifier: MIT
import pathlib, tempfile, subprocess, os.path

from .core import FWPackage
from .wifi import WiFiFWCollection
from .bluetooth import BluetoothFWCollection
from .radio_calibration import BluetoothCalibration, WiFiCalibration
from .multitouch import MultitouchFWCollection
from .kernel import KernelFWCollection
from .isp import ISPFWCollection
from .als import AlsFWCollection
from .open_firmware import OpenFirmwareCollection

def update_firmware(source, dest, machine=None, open_firmware=None):
    raw_fw = source.joinpath("all_firmware.tar.gz")
    if not raw_fw.exists():
        raise FileNotFoundError(f"Could not find {raw_fw}")

    dest.mkdir(parents=True, exist_ok=True)
    pkg = FWPackage(dest)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        subprocess.run(["tar", "xf", str(raw_fw.resolve())], cwd=tmpdir, check=True)

        wifi_sources = (
            tmpdir.joinpath("apple_bcmwlan_firmware"),
            tmpdir.joinpath("firmware", "wifi"),
        )
        wifi_source = next((path for path in wifi_sources if path.is_dir()), None)
        if wifi_source is None:
            raise FileNotFoundError("Could not find raw Wi-Fi firmware")

        col = WiFiFWCollection(str(wifi_source), machine=machine)
        pkg.add_files(sorted(col.files()))

        col = BluetoothFWCollection(
            str(tmpdir.joinpath("firmware", "bluetooth")), machine=machine
        )
        pkg.add_files(sorted(col.files()))

        if machine == "j773g":
            for kind in (BluetoothCalibration, WiFiCalibration):
                calibration = kind.from_archive(tmpdir)
                if calibration is not None:
                    pkg.add_files(calibration.files())

        col = MultitouchFWCollection(str(tmpdir.joinpath("fud_firmware")))
        pkg.add_files(sorted(col.files()))

        if machine != "j773g":
            col = ISPFWCollection(str(tmpdir))
            pkg.add_files(sorted(col.files()))

            col = AlsFWCollection(str(tmpdir))
            pkg.add_files(sorted(col.files()))

    col = KernelFWCollection(str(source))
    pkg.add_files(sorted(col.files()))

    col = OpenFirmwareCollection(machine=machine, source_path=open_firmware)
    pkg.add_files(sorted(col.files()))

    pkg.close()

def main():
    import argparse
    import logging
    logging.basicConfig()

    parser = argparse.ArgumentParser(description='Update vendor firmware tarball')
    parser.add_argument('source', metavar='SOURCE', type=pathlib.Path,
                        help='path containing raw firmware')
    parser.add_argument('dest', metavar='DEST', type=pathlib.Path,
                        help='output path for vendor firmware')
    parser.add_argument('--machine', choices=('j773g',), required=True,
                        help='machine profile for required generic aliases')
    parser.add_argument('--open-firmware', type=pathlib.Path,
                        help='root containing open firmware to add')
    args = parser.parse_args()

    update_firmware(args.source, args.dest, machine=args.machine,
                    open_firmware=args.open_firmware)

if __name__ == "__main__":
    main()
