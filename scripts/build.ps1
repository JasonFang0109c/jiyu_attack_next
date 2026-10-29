[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$Version = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item -LiteralPath $PSScriptRoot).Parent.FullName
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "未找到解释器，请先创建 .venv 或使用 -Python 指定解释器。"
    }
    $pythonExe = (Resolve-Path -LiteralPath $Python).Path
    $buildRoot = Join-Path $projectRoot "build"
    $outputRoot = Join-Path $projectRoot "output"
    $exePath = Join-Path $outputRoot "JiYuAttackNext.exe"
    $runningApp = Get-Process -Name "JiYuAttackNext.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $exePath }
    if ($runningApp) {
        throw "请关闭正在运行的 JiYuAttackNext.exe 后再构建。"
    }
    & $pythonExe -X utf8 -c "import PySide6.QtWidgets, qfluentwidgets, PyInstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "缺少构建依赖，请先执行：python -m pip install -r requirements.txt"
    }

    if (-not $Version) {
        $Version = (& $pythonExe -X utf8 -c "import app; print(app.__version__)").Trim()
        if ($LASTEXITCODE -ne 0 -or -not $Version) {
            throw "无法从 app/__init__.py 读取版本号，请使用 -Version 指定。"
        }
    }
    $versionPattern = '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$'
    if ($Version -notmatch $versionPattern) {
        throw "版本号不符合语义化版本格式（如 0.4.0 或 0.4.0-nightly.20261029）：$Version"
    }

    New-Item -ItemType Directory -Path (Join-Path $buildRoot "assets") -Force | Out-Null
    $iconScript = "from PySide6.QtGui import QGuiApplication, QIcon; from PySide6.QtCore import QSize; app = QGuiApplication([]); icon = QIcon('assets/app.svg'); ok = icon.pixmap(QSize(256, 256)).save('build/assets/app.ico', 'ICO'); raise SystemExit(0 if ok else 1)"
    & $pythonExe -X utf8 -c $iconScript
    if ($LASTEXITCODE -ne 0) {
        throw "图标转换失败，退出码：$LASTEXITCODE"
    }
    $buildTimeScript = "from app.gui.build_info import write_build_time; write_build_time('build/assets/build_time.txt')"
    & $pythonExe -X utf8 -c $buildTimeScript
    if ($LASTEXITCODE -ne 0) {
        throw "构建时间写入失败，退出码：$LASTEXITCODE"
    }
    $versionScript = "from app.gui.build_info import write_version; write_version('build/assets/version.txt', '$Version')"
    & $pythonExe -X utf8 -c $versionScript
    if ($LASTEXITCODE -ne 0) {
        throw "版本号写入失败，退出码：$LASTEXITCODE"
    }

    # 生成 PyInstaller 的 Windows 版本资源，使 EXE 属性中显示版本号。
    & $pythonExe -X utf8 (Join-Path $PSScriptRoot "gen_version_info.py") $Version (Join-Path $buildRoot "assets\version_info.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "版本资源生成失败，退出码：$LASTEXITCODE"
    }

    $buildArguments = @(
        "-m", "PyInstaller", "--noconfirm",
        "--distpath", $outputRoot, "--workpath", $buildRoot
    )
    if ($Clean) {
        $buildArguments += "--clean"
    }
    $buildArguments += (Join-Path $PSScriptRoot "JiYuAttackNext.spec")
    & $pythonExe @buildArguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
    }
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw "未找到构建产物：$exePath"
    }
    $legacyPath = Join-Path $outputRoot "JiyuUdpTest.exe"
    if (Test-Path -LiteralPath $legacyPath -PathType Leaf) {
        try {
            Remove-Item -LiteralPath $legacyPath -Force
        } catch {
            Write-Warning "旧版 JiyuUdpTest.exe 正在运行，无法移除；新版本已构建完成。"
        }
    }
    Write-Host ("构建完成：" + $exePath + "（版本 " + $Version + "）") -ForegroundColor Green
}
finally {
    Pop-Location
}
