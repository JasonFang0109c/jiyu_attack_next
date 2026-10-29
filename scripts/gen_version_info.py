"""生成 PyInstaller 使用的 Windows 版本资源文件。

由 scripts/build.ps1 调用，使 EXE 属性中显示版本号。
用法：python scripts/gen_version_info.py <版本号> <输出路径>
"""

from pathlib import Path
import sys

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)


PRODUCT_NAME = "JiYu Attack Next"
INTERNAL_NAME = "JiYuAttackNext"


def numeric_parts(version):
    """把版本号的核心段转换为四个整数；预发布与构建后缀不参与。"""
    core = version.split("-", 1)[0].split("+", 1)[0]
    parts = [int(value) for value in core.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def build_version_info(version):
    """构造包含版本号的 VSVersionInfo 对象。"""
    numbers = numeric_parts(version)
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("080404b0", [
                StringStruct("FileDescription", PRODUCT_NAME),
                StringStruct("FileVersion", version),
                StringStruct("InternalName", INTERNAL_NAME),
                StringStruct("OriginalFilename", INTERNAL_NAME + ".exe"),
                StringStruct("ProductName", PRODUCT_NAME),
                StringStruct("ProductVersion", version),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
        ],
    )


def write_version_info(path, version):
    """把版本资源写入指定路径。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(build_version_info(version)), encoding="utf-8")
    return target


def main(argv):
    if len(argv) != 3:
        print("用法：python scripts/gen_version_info.py <版本号> <输出路径>",
              file=sys.stderr)
        return 2
    target = write_version_info(argv[2], argv[1])
    print("已生成版本资源：%s（版本 %s）" % (target, argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
