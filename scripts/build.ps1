[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe",
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
    $exePath = Join-Path $outputRoot "JiyuUdpTest.exe"
    $runningApp = Get-Process -Name "JiyuUdpTest" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $exePath }
    if ($runningApp) {
        throw "请关闭正在运行的 JiyuUdpTest.exe 后再构建。"
    }
    & $pythonExe -X utf8 -c "import PySide6.QtWidgets, qfluentwidgets, PyInstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "缺少构建依赖，请先执行：python -m pip install -r requirements.txt"
    }

    New-Item -ItemType Directory -Path (Join-Path $buildRoot "assets") -Force | Out-Null
    $iconScript = "from PySide6.QtGui import QGuiApplication, QIcon; from PySide6.QtCore import QSize; app = QGuiApplication([]); icon = QIcon('assets/app.svg'); ok = icon.pixmap(QSize(256, 256)).save('build/assets/app.ico', 'ICO'); raise SystemExit(0 if ok else 1)"
    & $pythonExe -X utf8 -c $iconScript
    if ($LASTEXITCODE -ne 0) {
        throw "图标转换失败，退出码：$LASTEXITCODE"
    }

    $buildArguments = @(
        "-m", "PyInstaller", "--noconfirm",
        "--distpath", $outputRoot, "--workpath", $buildRoot
    )
    if ($Clean) {
        $buildArguments += "--clean"
    }
    $buildArguments += (Join-Path $PSScriptRoot "JiyuUdpTest.spec")
    & $pythonExe @buildArguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
    }
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw "未找到构建产物：$exePath"
    }
    Write-Host ("构建完成：" + $exePath) -ForegroundColor Green
}
finally {
    Pop-Location
}
