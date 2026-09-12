#!/usr/bin/env bash
# Wrap dist/keyflip.app in a drag-to-install disk image.
# Run after build_macos.sh:  ./packaging/build_dmg.sh [version] [arch-suffix]
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/keyflip/app.py)}"
SUFFIX="${2:-}"
APP="dist/keyflip.app"
DMG="dist/keyflip-${VERSION}${SUFFIX:+-$SUFFIX}.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

[ -d "$APP" ] || { echo "no $APP - run ./packaging/build_macos.sh first" >&2; exit 1; }

# The symlink is the whole trick: the window shows keyflip beside a shortcut
# to /Applications, so installing is one drag.  It also matters for more than
# tidiness - an app launched from inside a downloaded disk image runs under
# App Translocation from a random read-only path, where an Accessibility grant
# can never stick.  Dragging it out first is what avoids that.
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp README.md "$STAGE/README.md"

rm -f "$DMG"
hdiutil create -volname "keyflip $VERSION" -srcfolder "$STAGE" \
    -ov -format UDZO -quiet "$DMG"

echo "Built $DMG"
