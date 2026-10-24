#!/bin/bash
# Install or update keyflip on a Mac, with no Gatekeeper dialog to get past.
#
#   curl -fsSL https://raw.githubusercontent.com/Punnawit9285/keyflip/main/install.sh | bash
#
# A browser stamps everything it downloads with com.apple.quarantine, and that
# stamp is the whole reason macOS refuses to open keyflip: the build is not
# notarized, and since macOS 15 the only way past is a trip to Privacy &
# Security for "Open Anyway" - on every update, too.  curl does not stamp
# anything, so a copy fetched here is simply never checked.  The app is still
# verified before it goes in: its signature seals every file in the bundle.
#
# KEYFLIP_DMG=/path/to/keyflip.dmg installs that file instead of downloading
# the latest release; CI uses it to try a build before releasing it.
set -euo pipefail

REPO="Punnawit9285/keyflip"
APP="/Applications/keyflip.app"

say() { printf '%s\n' "$*"; }
die() { printf 'keyflip: %s\n' "$*" >&2; exit 1; }

tmp=""
mnt=""
cleanup() {
    if [ -n "$mnt" ]; then
        hdiutil detach "$mnt" -quiet 2>/dev/null ||
            hdiutil detach "$mnt" -force -quiet 2>/dev/null || return 0
    fi
    # Only once the image is gone - otherwise this would reach into it.
    [ -z "$tmp" ] || rm -rf "$tmp"
}

download() {
    # Apple silicon even from a Terminal running under Rosetta, where
    # uname -m says x86_64.
    local arch=x86_64
    [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ] && arch=arm64

    # /releases/latest redirects to /releases/tag/v<version>, which names the
    # asset: packaging/build_dmg.sh calls it keyflip-<version>-<arch>.dmg.
    local url tag
    url="$(curl -fsSL -o /dev/null -w '%{url_effective}' \
        "https://github.com/$REPO/releases/latest")" ||
        die "could not reach GitHub - check your connection and try again"
    tag="${url##*/}"
    case "$tag" in v[0-9]*) ;; *) die "could not find the latest release at $url" ;; esac

    local name="keyflip-${tag#v}-$arch.dmg"
    say "Downloading $name ..."
    curl -fL --progress-bar -o "$tmp/$name" \
        "https://github.com/$REPO/releases/download/$tag/$name" ||
        die "download failed - try again"
    dmg="$tmp/$name"
}

quit_running() {
    # A running copy is the old build: it would keep the old binary alive and,
    # once this one starts, two of them would answer every double tap.
    pgrep -x keyflip >/dev/null || return 0
    say "Quitting the keyflip that is running ..."
    pkill -x keyflip || true
    local _
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        pgrep -x keyflip >/dev/null || return 0
        sleep 0.5
    done
    pkill -9 -x keyflip || true
}

main() {
    [ "$(uname -s)" = Darwin ] ||
        die "this installer is for macOS - on Windows, download the -setup.exe from https://github.com/$REPO/releases"

    tmp="$(mktemp -d "${TMPDIR:-/tmp}/keyflip.XXXXXX")"
    trap cleanup EXIT

    dmg="${KEYFLIP_DMG:-}"
    [ -n "$dmg" ] || download
    [ -f "$dmg" ] || die "no such file: $dmg"

    mnt="$tmp/mnt"
    mkdir "$mnt"
    # stdin is the script itself under curl | bash; nothing may read from it.
    hdiutil attach -nobrowse -noautoopen -readonly -quiet \
        -mountpoint "$mnt" "$dmg" </dev/null ||
        { mnt=""; die "could not open the disk image - try again"; }

    local new="$mnt/keyflip.app"
    [ -d "$new" ] || die "the disk image has no keyflip.app in it"
    # A broken seal is what macOS reports as "damaged": refuse it here rather
    # than replace a working copy with it.
    codesign --verify --deep --strict "$new" ||
        die "the downloaded app failed its signature check - try again"

    quit_running

    # Admin accounts can write to /Applications; anyone else needs sudo, as
    # does replacing a copy another account installed.
    local sudo=""
    if [ ! -w /Applications ] || { [ -e "$APP" ] && [ ! -O "$APP" ]; }; then
        say "Installing into /Applications needs an administrator password."
        sudo=sudo
    fi
    $sudo rm -rf "$APP"
    $sudo ditto "$new" "$APP"
    # Only there if the image itself came from a browser (KEYFLIP_DMG).
    $sudo xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

    local version
    version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
        "$APP/Contents/Info.plist" 2>/dev/null)" || version=""
    say ""
    say "keyflip${version:+ $version} is installed in /Applications."

    if open "$APP"; then
        say ""
        say "It is starting now, and will ask for Accessibility permission:"
        say "  System Settings -> Privacy & Security -> Accessibility -> turn on keyflip"
        say "It starts by itself the moment you do. Then select text typed in the"
        say "wrong layout and tap the right Shift twice."
    else
        say "Open it from Applications to start it."
    fi
}

main
