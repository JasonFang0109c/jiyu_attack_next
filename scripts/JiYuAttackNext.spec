# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata


root = Path(SPECPATH).parent
icon = root / "build" / "assets" / "app.ico"
build_time = root / "build" / "assets" / "build_time.txt"
version_file = root / "build" / "assets" / "version.txt"
version_info = root / "build" / "assets" / "version_info.txt"

a = Analysis(
    [str(root / "app" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets" / "app.svg"), "assets")]
          + ([(str(build_time), ".")] if build_time.exists() else [])
          + ([(str(version_file), ".")] if version_file.exists() else [])
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
    # 统一入口需要控制台承载 CLI 输出；双击时由 bootloader 隐藏自有控制台。
    console=True,
    hide_console="hide-early",
    # 不随程序启动请求管理员权限，避免终端启动时另开提升的控制台；
    # 防火墙操作在需要时通过 UAC 启动隐藏助手。
    uac_admin=False,
    icon=str(icon) if icon.exists() else None,
    version=str(version_info) if version_info.exists() else None,
)
