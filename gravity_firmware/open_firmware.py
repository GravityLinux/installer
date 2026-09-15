# SPDX-License-Identifier: MIT
import os
from pathlib import Path

from .core import FWFile


# These files are built from open source and bundled with the installer.  They
# are deliberately kept separate from firmware extracted from macOS so their
# provenance is unambiguous.
MACHINE_FILES = {
    # AVD is not part of the first M4 release. No bundled open firmware needed.
    "j773g": (),
}


class OpenFirmwareCollection(object):
    def __init__(self, machine=None, source_path=None):
        if machine is not None and machine not in MACHINE_FILES:
            raise ValueError(f"Unknown open-firmware machine profile: {machine}")

        self.fwfiles = []
        if machine is None:
            return

        if source_path is None:
            source_path = os.environ.get("GRAVITY_OPEN_FIRMWARE")
        if source_path is None:
            source_path = Path(__file__).parent / "data"
        else:
            source_path = Path(source_path)

        for name in MACHINE_FILES[machine]:
            path = source_path / name
            if not path.exists():
                # The avd-fw Makefile writes directly into its build directory,
                # while installed/bundled firmware uses the apple/ hierarchy.
                flat_path = source_path / Path(name).name
                if flat_path.exists():
                    path = flat_path
            try:
                data = path.read_bytes()
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Missing open firmware for {machine}: {path}"
                ) from None
            self.fwfiles.append((name, FWFile(str(path), data)))

    def files(self):
        return self.fwfiles
