#!/usr/bin/env bash
# Build keyflip.app.  Run from the repo root:  ./packaging/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
"$PY" -m pip install --quiet --upgrade pyinstaller
rm -rf build dist
"$PY" -m PyInstaller --noconfirm --clean packaging/keyflip-macos.spec

# Sign the bundle as a whole: an arm64 binary will not run unsigned.  Ad-hoc
# does NOT keep the Accessibility grant across builds, though - its identity
# is the binary's hash, which every build changes, so each update has to be
# granted again.  keyflip clears the old build's entry at launch
# (backend_mac.forget_stale_permission) so that is one switch to flip; only a
# real signing certificate would remove the step.
codesign --force --deep --sign - dist/keyflip.app

echo
echo "Built dist/keyflip.app"
echo "  1. Move it to /Applications"
echo "  2. Open it once and grant Accessibility when it asks:"
echo "     System Settings > Privacy & Security > Accessibility"
echo "     (it starts by itself as soon as you do)"
echo "  3. Start at login is a tick in its menu-bar menu"
echo
echo "  ./packaging/build_dmg.sh   wraps it in a drag-to-install disk image"
