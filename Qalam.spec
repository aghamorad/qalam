# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Qalam.app.

Build with:  .venv/bin/pyinstaller Qalam.spec --noconfirm

Two things here are load-bearing and were both learned the hard way:

`pathex` has to include the repo root. The package is normally installed
editable, and the editable finder is not something PyInstaller's static analysis
can follow, so without this the bundle builds cleanly and then dies at launch
with "No module named persian_ebook.gui".

The version comes from `persian_ebook.__version__` rather than a literal, so the
About box, the window title and the app bundle cannot drift apart.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT))

from persian_ebook import __version__  # noqa: E402

VERSION = __version__
DATA = ("persian_ebook/data", "persian_ebook/data")

a = Analysis(
    ["tools/launch_gui.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[DATA],
    hiddenimports=["persian_ebook.gui", "persian_ebook.convert"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Qalam",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="persian_ebook/data/icon.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Qalam",
)

app = BUNDLE(
    coll,
    name="Qalam.app",
    icon="persian_ebook/data/icon.icns",
    bundle_identifier="ir.morad.qalam",
    info_plist={
        "CFBundleName": "Qalam",
        "CFBundleDisplayName": "Qalam",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHumanReadableCopyright": "MIT © 2026 Morad",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        # The app reads the user's own PDFs from wherever they keep them.
        "LSApplicationCategoryType": "public.app-category.productivity",
    },
)
