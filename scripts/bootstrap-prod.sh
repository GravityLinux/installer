#!/bin/sh
# SPDX-License-Identifier: MIT

# Truncation guard
if true; then
    set -e

    if [ ! -e /System ]; then
        echo "You appear to be running this script from Linux or another non-macOS system."
        echo "Gravity Linux can only be installed from macOS (or recoveryOS)."
        exit 1
    fi

    export LC_ALL=en_US.UTF-8
    export LANG=en_US.UTF-8
    export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

    if ! curl --no-progress-meter file:/// >/dev/null 2>&1; then
        echo "Your version of cURL is too old. This usually means your macOS is very out"
        echo "of date. Installing Gravity Linux requires at least macOS version 26.6.2."
        exit 1
    fi

    export DISTRO="Gravity Linux"
    export DISTRO_DOCS=https://gravitylinux.org/docs
    export VERSION_FLAG=https://cdn.gravitylinux.org/installer/latest
    export INSTALLER_BASE=https://cdn.gravitylinux.org/installer
    export INSTALLER_DATA=https://cdn.gravitylinux.org/installer/installer_data.json
    export REPO_BASE=https://cdn.gravitylinux.org

    #TMP="$(mktemp -d)"
    TMP=/tmp/gravity-install

    echo
    echo "Bootstrapping installer:"

    if [ -e "$TMP" ]; then
        mv "$TMP" "$TMP-$(date +%Y%m%d-%H%M%S)"
    fi

    mkdir -p "$TMP"
    cd "$TMP"

    echo "  Checking version..."

    PKG_VER="$(curl --no-progress-meter -L "$VERSION_FLAG")"
    echo "  Version: $PKG_VER"

    PKG="installer-$PKG_VER.tar.gz"

    echo "  Downloading..."

    curl --no-progress-meter -L -o "$PKG" "$INSTALLER_BASE/$PKG"
    curl --no-progress-meter -L -O "$INSTALLER_DATA"

    echo "  Extracting..."

    tar xf "$PKG"

    echo "  Initializing..."
    echo

    if [ "$USER" != "root" ]; then
        echo "The installer needs to run as root."
        echo "Please enter your sudo password if prompted."
        exec caffeinate -dis sudo -E ./install.sh "$@"
    else
        exec caffeinate -dis ./install.sh "$@"
    fi
fi
