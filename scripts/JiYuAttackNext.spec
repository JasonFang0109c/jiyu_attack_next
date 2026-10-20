# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata


root = Path(SPECPATH).parent
icon = root / "build" / "assets" / "app.ico"

a = Analysis(
    [str(root / "app" / "gui" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets" / "app.svg"), "assets")]
          + copy_metadata("PySide6") + copy_metadata("PySide6-Fluent-Widgets"),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="JiYu Attack Next",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    uac_admin=True,
    icon=str(icon) if icon.exists() else None,
)