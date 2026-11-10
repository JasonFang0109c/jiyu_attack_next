# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata


root = Path(SPECPATH).parent
icon = root / "build" / "assets" / "app.ico"
build_time = root / "build" / "assets" / "build_time.txt"
version_file = root / "build" / "assets" / "version.txt"
version_info = root / "build" / "assets" / "version_info.txt"
variant_file = root / "build" / "assets" / "variant.txt"
# 构建脚本通过环境变量声明变体与产物名：debug 版本换前缀，其余完全一致。
# 产物名直接带版本号，PyInstaller 一次写出最终文件，不再落一份固定名再复制。
variant = os.environ.get("JY_BUILD_VARIANT", "release").strip().lower()
default_name = "JiYuAttackNext_Debug" if variant == "debug" else "JiYuAttackNext"
exe_name = os.environ.get("JY_BUILD_NAME", "").strip() or default_name

a = Analysis(
    [str(root / "app" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "app" / "resources" / "icons" / "app.svg"), "app/resources/icons")]
          + ([(str(build_time), ".")] if build_time.exists() else [])
          + ([(str(version_file), ".")] if version_file.exists() else [])
          + ([(str(variant_file), ".")] if variant_file.exists() else [])
          + copy_metadata("PySide6")
          + copy_metadata("PySide6-Fluent-Widgets"),
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
# 用不上的 Qt 组件：软件 OpenGL 渲染器、QML/Quick 运行时、PDF 模块、
# 虚拟键盘，以及只服务于这些模块的插件。界面只用 Widgets，运行期不会
# 加载 QML，也不会显示 PDF。
QT_UNUSED_BINARIES = {
    "opengl32sw.dll",
    "qt6opengl.dll",
    "qt6openglwidgets.dll",
    "qt6pdf.dll",
    "qt6pdfquick.dll",
    "qt6pdfwidgets.dll",
    "qt6qml.dll",
    "qt6qmlmeta.dll",
    "qt6qmlmodels.dll",
    "qt6qmlworkerscript.dll",
    "qt6quick.dll",
    "qt6quickcontrols2.dll",
    "qt6quickparticles.dll",
    "qt6quickshapes.dll",
    "qt6quicktemplates2.dll",
    "qt6quickwidgets.dll",
    "qt6virtualkeyboard.dll",
}
QT_UNUSED_PLUGINS = {
    "qdirect2d.dll",
    "qgif.dll",
    "qicns.dll",
    "qminimal.dll",
    "qoffscreen.dll",
    "qpdf.dll",
    "qtga.dll",
    "qtiff.dll",
    "qtuiotouchplugin.dll",
    "qtvirtualkeyboardplugin.dll",
    "qwebp.dll",
}
# Build hosts can expose incompatible ICU DLLs (for example via Poppler).
# PySide6 uses the Windows system ICU DLL; keep unrelated PATH copies out.
ICU_UNUSED = {"icuuc.dll", "icuin.dll", "icudt78.dll", "icuio78.dll"}


def _stem(name):
    """去掉扩展名与 ABI 标记，用于匹配带 ABI 后缀的扩展模块名。"""
    return Path(name).name.split(".")[0].casefold()


def _is_qt_translation(name):
    """判断是否为 Qt 自带翻译文件，这些文件运行期不会被加载。"""
    parts = Path(name).parts
    return "translations" in parts and Path(name).suffix.casefold() == ".qm"


a.binaries = [
    entry
    for entry in a.binaries
    if Path(entry[0]).name.casefold() not in ICU_UNUSED
    and Path(entry[0]).name.casefold() not in QT_UNUSED_BINARIES
    and Path(entry[0]).name.casefold() not in QT_UNUSED_PLUGINS
    and _stem(entry[0]) not in PILLOW_UNUSED
    and not _is_qt_translation(entry[0])
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 窗口化子系统：双击启动不会创建控制台窗口。带参数运行时由
    # app/start/console.py 把输出接回调用方的控制台。
    console=False,
    # 不随程序启动请求管理员权限，避免终端启动时另开提升的控制台；
    # 防火墙操作在需要时通过 UAC 启动隐藏助手。
    uac_admin=False,
    icon=str(icon) if icon.exists() else None,
    version=str(version_info) if version_info.exists() else None,
)
