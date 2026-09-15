#!/bin/sh
set -e

cd "$(dirname "$0")"
base="$PWD"

if [ -e "$HOME/.cargo/env" ] ; then
    . "$HOME/.cargo/env"
fi

export INSTALLER_BASE=https://cdn.gravitylinux.org/installer-dev
export REPO_BASE=https://cdn.gravitylinux.org

make -C "bootloader" RELEASE=1 CHAINLOADING=1 -j4

sudo rm -rf /tmp/gravity-install
mkdir -p /tmp/gravity-install

git describe --tags --always --dirty > /tmp/gravity-install/version.tag

cd /tmp/gravity-install
ln -sf "$base/src"/* .
ln -sf "$base/gravity_firmware" .
mkdir -p boot
cp "$base/bootloader/build/m1n1.bin" boot/m1n1.bin
sh "$base/tools/append-boot-logo.sh" boot/m1n1.bin "$base/artwork"
ln -sf "$base/artwork/logos/icns/GravityLinux_logomark.icns" logo.icns
ln -sf "$base/data/installer_data.json" installer_data.json

sudo -E python3 main.py
