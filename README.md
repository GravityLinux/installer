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

Run firmware tests with `python3 -m unittest discover -s tests`.

## License

This project is distributed under the MIT license. See [LICENSE](LICENSE).
Upstream copyright notices are retained where required by that license.
