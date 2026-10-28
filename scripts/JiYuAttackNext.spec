# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata


root = Path(SPECPATH).parent
icon = root / "build" / "assets" / "app.ico"
build_time = root / "build" / "assets" / "build_time.txt"

a = Analysis(
    [str(root / "app" / "gui" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets" / "app.svg"), "assets")]
          + ([(str(build_time), ".")] if build_time.exists() else [])
          + copy_metadata("PySide6") + copy_metadata("PySide6-Fluent-Widgets"),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# Build hosts can expose incompatible ICU DLLs (for example via Poppler).
# PySide6 uses the Windows system ICU DLL; keep unrelated PATH copies out.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.casefold() not in {
    "icuuc.dll", "icuin.dll", "icudt78.dll", "icuio78.dll",
}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="JiYuAttackNext",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    uac_admin=True,
    icon=str(icon) if icon.exists() else None,
)
