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
    # 组件库只用 scipy.ndimage 做高斯模糊，其余子包不会在运行时导入。
    # scipy.linalg 与 scipy.special 是 ndimage 的依赖，不能排除。
    excludes=[
        "scipy.cluster",
        "scipy.constants",
        "scipy.datasets",
        "scipy.differentiate",
        "scipy.fft",
        "scipy.fftpack",
        "scipy.integrate",
        "scipy.interpolate",
        "scipy.io",
        "scipy.misc",
        "scipy.odr",
        "scipy.optimize",
        "scipy.signal",
        "scipy.sparse",
        "scipy.spatial",
        "scipy.stats",
    ],
    noarchive=False,
)
# Pillow 的 AVIF 与 Tk 插件不会被组件库用到，留着只会白占体积。
PILLOW_UNUSED = {"_avif", "_imagingtk"}
# Build hosts can expose incompatible ICU DLLs (for example via Poppler).
# PySide6 uses the Windows system ICU DLL; keep unrelated PATH copies out.
a.binaries = [
    entry
    for entry in a.binaries
    if Path(entry[0]).name.casefold()
    not in {"icuuc.dll", "icuin.dll", "icudt78.dll", "icuio78.dll"}
    and Path(entry[0]).stem.casefold() not in PILLOW_UNUSED
]
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
    # 窗口化子系统：双击启动不会创建控制台窗口。带参数运行时由
    # app/__main__.py 把输出接回调用方的控制台。
    console=False,
    # 不随程序启动请求管理员权限，避免终端启动时另开提升的控制台；
    # 防火墙操作在需要时通过 UAC 启动隐藏助手。
    uac_admin=False,
    icon=str(icon) if icon.exists() else None,
    version=str(version_info) if version_info.exists() else None,
)
