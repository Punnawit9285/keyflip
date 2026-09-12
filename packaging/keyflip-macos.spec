# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS menu-bar app.

LSUIElement is the important line: it makes keyflip a background agent with a
menu-bar item and no Dock tile, which is what a shortcut utility should be.
"""
import pathlib

ROOT = pathlib.Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    hiddenimports=[
        "keyflip.backend_mac",
        "keyflip.tray_mac",
    ],
    excludes=["tkinter", "pytest", "PIL", "pystray"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="keyflip",
          console=False, debug=False, strip=False, upx=False,
          target_arch=None, codesign_identity=None)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="keyflip")

app = BUNDLE(
    coll,
    name="keyflip.app",
    bundle_identifier="com.keyflip.app",
    version="1.0.0",
    info_plist={
        "LSUIElement": True,                 # menu-bar only, no Dock icon
        "CFBundleName": "keyflip",
        "CFBundleDisplayName": "keyflip",
        "CFBundleShortVersionString": "1.0.0",
        "NSHumanReadableCopyright": "MIT",
        "LSMinimumSystemVersion": "11.0",
    },
)
