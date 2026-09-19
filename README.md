# Gravity Linux installer

The Gravity Linux installer installs Gravity Linux on exactly one Apple Silicon
model: the M4 Mac mini (`t8132`, `j773gap`). It prepares the Apple boot chain,
installs the selected Gravity Linux image, and collects the device firmware
needed by that installation.

## User installation link

Publish the production bootstrap script at
`https://install.gravitylinux.org`, then direct users to run:

```sh
curl -fsSL https://install.gravitylinux.org | sh
```

That script is the stable public entry point. It obtains the current installer
version and metadata from the CDN, so the command itself does not need to change
on each release.

## CDN release layout

The production bootstrap expects these objects:

```
https://install.gravitylinux.org
https://cdn.gravitylinux.org/installer/latest
https://cdn.gravitylinux.org/installer/installer-<version>.tar.gz
https://cdn.gravitylinux.org/installer/installer_data.json
https://cdn.gravitylinux.org/os/<paths referenced by installer_data.json>
```

`installer-<version>.tar.gz` contains the packaged Python installer and m1n1
stage 1 (`boot/m1n1.bin`). Build it with `./build.sh` after initializing the
Gravity-owned `artwork` and `bootloader` submodules. `LOGO=/path/to/logo.icns` can
override the default `GravityLinux_logomark.icns` asset.

Stage 2 is not a standalone CDN bootstrap object. Build it as part of every
Gravity OS image: m1n1 plus U-Boot and the M4 Mac mini device trees. Publish
that image and its associated artifacts beneath `/os/`, and reference their
relative paths and checksums from `installer_data.json`.

The installer metadata and OS images are distribution release inputs. Fork or
create a Gravity-owned replacement for the installer-data repository, retain
only the `j773gap` device configuration, and change every image URL, checksum,
name, and support URL to Gravity-owned resources before publishing.

## Development and release

`scripts/bootstrap.sh` is for a local server. `scripts/bootstrap-dev.sh` and
`scripts/bootstrap-prod.sh` are configured for the Gravity CDN. The production
release workflow must use Gravity-owned storage credentials; it must not retain
the upstream storage-zone URL or secrets.

The `artwork` and `bootloader` submodules are sourced from Gravity Linux repositories.
Keep the bootloader's stage-1 and stage-2 M4 support in lockstep with this installer.

The checked-out submodule revisions now match the local Gravity artwork and
M4 bootloader sources. Those commits must be available at the URLs in
`.gitmodules` before recursive cloning or CI can work from GitHub.

The Python package and command are `gravity_firmware` and `gravity-fwextract`.
The `src/gravity_firmware` symlink supports running directly from the source
tree; the release bundle contains a real copy of that module.
No AVD build or bundled AVD firmware is required for this release.

Run tests with `PYTHONPATH=src:. python3 -m unittest discover -s tests`.

### macOS 26.6.2 recovery preflight

The qualified `UniversalMac_26.6.2_25G83_Restore.ipsw` stores BaseSystem as
`022-22048-093.dmg.aea`, not a mountable DMG. Before creating partitions, the
installer stages that member, verifies its SHA-256, decodes it with macOS's
`/usr/bin/aea`, verifies the decoded SHA-256 and DMG checksums, and mounts it
read-only to validate the recovery version and required M4 Wi-Fi/Bluetooth
firmware profiles. The decoded bytes, not the AEA wrapper, are then installed
with the existing transparent APFS compression path.

`src/recovery.py` pins the exact archive, decoded image and Apple-published
release key. This key is not a machine secret; its provenance is documented in
that module. Adding another IPSW requires qualifying new pins. No key-server
request or third-party decryption binary is needed during installation. Allow
at least 4 GiB of temporary free space for decoding. Temporary mounts use unique
directories and are detached even if firmware collection fails.

Native integration test (macOS, with the installer Python environment or a
working Python 3 installation; requires permission to set file compression):

```sh
PYTHONPATH=src:tests python3 tests/validate_m4_recovery_macos.py \
    /path/to/UniversalMac_26.6.2_25G83_Restore.ipsw /path/to/new-test-output
```

An HTTPS IPSW URL can replace the local path. This test runs the actual decoder,
compression and firmware collectors, validates the CPIO/TAR inventory, and
checks that disk0's partition layout is unchanged. It does not invoke the
interactive installer, partition disks, personalize boot objects or change boot
policy. A passing test validates the packaging pipeline, not hardware support
or a completed installation. Output is retained for inspection.

## License

This project is distributed under the MIT license. See [LICENSE](LICENSE).
Upstream copyright notices are retained where required by that license.

### M4 Bluetooth factory calibration

For J773g, firmware collection reads the local machine's
`BWCl-sakhalin-4388-C2-*` factory records and extracts the opaque `BTBF`
beamforming payload. It checks the IMG4/IM4P and record structure, size and
`BLOB` marker; it does not verify Apple's signature. Conflicting records are
rejected. No factory record or calibration data is bundled with the installer.

The `/chosen` Bluetooth address binds the output to its radio:
`vendorfw/u-boot/brcm/brcmbt4388-<12 lowercase hex address digits>-bf.bin`
on the ESP. The raw firmware archive saves the payload, address, SHA-256 and
source-record hashes so `gravity-fwextract` can reproduce it during updates.
U-Boot loads only the file matching the live DT address and supplies
`brcm,taurus-bf-cal-blob` before Linux boots. Linux consumes the DT property.
Older archives without calibration remain usable but cannot supply Bluetooth
calibration; recollect firmware on the original Mac to add it.
