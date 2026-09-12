#!/usr/bin/env bash
# Build keyflip.app.  Run from the repo root:  ./packaging/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
"$PY" -m pip install --quiet --upgrade pyinstaller
rm -rf build dist
"$PY" -m PyInstaller --noconfirm --clean packaging/keyflip-macos.spec

# Ad-hoc signing is not optional in practice.  macOS pins an Accessibility
# grant to the binary's identity; an unsigned bundle gets a new identity on
# every rebuild, so the permission silently stops applying and the hotkey goes
# dead until you toggle it off and on again.  A stable ad-hoc signature keeps
# the grant across rebuilds.
codesign --force --deep --sign - dist/keyflip.app

echo
echo "Built dist/keyflip.app"
echo "  1. Move it to /Applications"
echo "  2. Open it once, then grant it Accessibility permission:"
echo "     System Settings > Privacy & Security > Accessibility"
echo "  3. To start it at login: System Settings > General > Login Items > +"
