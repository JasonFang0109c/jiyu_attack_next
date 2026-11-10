[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$Version = "",
    # 提交哈希：产物文件名与版本资源都带它；留空时自动取当前提交。
    [string]$Commit = "",
    # 默认同时产出正常版本与 debug 版本：两个 EXE 只差日志等级，源码同一份。
    [ValidateSet("both", "release", "debug")]
    [string]$Variant = "both",
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
    # 两个变体产出不同文件名，共用同一个 output 目录与数据目录。
    $targets = @(
        @{ Variant = "release"; Name = "JiYuAttackNext" },
        @{ Variant = "debug"; Name = "JiYuAttackNext_Debug" }
    )
    if ($Variant -ne "both") {
        $targets = @($targets | Where-Object { $_.Variant -eq $Variant })
    }
    & $pythonExe -X utf8 -c "import PySide6.QtWidgets, qfluentwidgets, PyInstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "缺少构建依赖，请先执行：python -m pip install -r requirements.txt"
    }

    if (-not $Version) {
        $Version = (& $pythonExe -X utf8 -c "import app; print(app.__version__)").Trim()
        if ($LASTEXITCODE -ne 0 -or -not $Version) {
            throw "无法从 app/shared/version.py 读取版本号，请使用 -Version 指定。"
        }
    }
    $versionPattern = '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$'
    if ($Version -notmatch $versionPattern) {
        throw "版本号不符合语义化版本格式（如 0.4.0 或 0.4.0-nightly.20261029）：$Version"
    }

    # 产物名与版本资源都带提交哈希，同一个版本号的不同构建才能区分开。
    # 没传 -Commit 时自动取当前提交；显式传空字符串表示不要哈希，正式版用它。
    $autoCommit = -not $PSBoundParameters.ContainsKey("Commit")
    if ($autoCommit -and -not $Commit) {
        $Commit = (& git rev-parse --short=7 HEAD 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $Commit) {
            $Commit = ""
            Write-Warning "不在 Git 仓库内，产物名与版本资源不带提交哈希。"
        } else {
            $Commit = $Commit.Trim()
        }
    }
    if ($Commit -and $Commit -notmatch '^[0-9A-Za-z]+$') {
        throw "提交哈希只能包含字母与数字：$Commit"
    }
    $displayVersion = $Version
    if ($Commit -and -not $Version.EndsWith("-" + $Commit)) {
        $displayVersion = "$Version-$Commit"
    }

    # 产物名带显示版本，重建同一版本时才会写到已存在（可能正在运行）的文件上。
    # 进程名不含扩展名；带 .exe 会让 -Name 匹配不到任何进程，导致保护形同虚设。
    foreach ($target in $targets) {
        $exeName = $target.Name + "-" + $displayVersion
        $runningPath = Join-Path $outputRoot ($exeName + ".exe")
        $runningApp = Get-Process -Name $exeName -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $runningPath }
        if ($runningApp) {
            throw ("请关闭正在运行的 " + $exeName + ".exe 后再构建。")
        }
    }

    New-Item -ItemType Directory -Path (Join-Path $buildRoot "assets") -Force | Out-Null
    $iconScript = "from PySide6.QtGui import QGuiApplication, QIcon; from PySide6.QtCore import QSize; app = QGuiApplication([]); icon = QIcon('app/resources/icons/app.svg'); ok = icon.pixmap(QSize(256, 256)).save('build/assets/app.ico', 'ICO'); raise SystemExit(0 if ok else 1)"
    & $pythonExe -X utf8 -c $iconScript
    if ($LASTEXITCODE -ne 0) {
        throw "图标转换失败，退出码：$LASTEXITCODE"
    }
    $buildTimeScript = "from app.shared.build_info import write_build_time; write_build_time('build/assets/build_time.txt')"
    & $pythonExe -X utf8 -c $buildTimeScript
    if ($LASTEXITCODE -ne 0) {
        throw "构建时间写入失败，退出码：$LASTEXITCODE"
    }
    $versionScript = "from app.shared.version import write_version; write_version('build/assets/version.txt', '$displayVersion')"
    & $pythonExe -X utf8 -c $versionScript
    if ($LASTEXITCODE -ne 0) {
        throw "版本号写入失败，退出码：$LASTEXITCODE"
    }

    # 生成 PyInstaller 的 Windows 版本资源，使 EXE 属性中显示版本号。
    & $pythonExe -X utf8 (Join-Path $PSScriptRoot "gen_version_info.py") $displayVersion (Join-Path $buildRoot "assets\version_info.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "版本资源生成失败，退出码：$LASTEXITCODE"
    }

    $variantPath = Join-Path $buildRoot "assets\variant.txt"
    foreach ($target in $targets) {
        # 变体标记随产物一起打包，运行时据此决定日志等级；不带 BOM，
        # 免得读回来的文本多出不可见字符导致判定失败。
        [System.IO.File]::WriteAllText($variantPath, $target.Variant)
        $env:JY_BUILD_VARIANT = $target.Variant
        # 产物名带上版本号，PyInstaller 直接写出最终文件名，不再另存固定名副本。
        $exeName = $target.Name + "-" + $displayVersion
        $env:JY_BUILD_NAME = $exeName
        # 每个变体用独立 workpath：共用会命中上一次的缓存，产物名字与变体对不上。
        $buildArguments = @(
            "-m", "PyInstaller", "--noconfirm",
            "--distpath", $outputRoot,
            "--workpath", (Join-Path $buildRoot $target.Variant)
        )
        if ($Clean) {
            $buildArguments += "--clean"
        }
        $buildArguments += (Join-Path $PSScriptRoot "JiYuAttackNext.spec")
        & $pythonExe @buildArguments
        if ($LASTEXITCODE -ne 0) {
            throw ("PyInstaller 构建 " + $target.Variant + " 版本失败，退出码：" + $LASTEXITCODE)
        }
        $exePath = Join-Path $outputRoot ($exeName + ".exe")
        if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
            throw "未找到构建产物：$exePath"
        }
        Write-Host ("构建完成：" + $exePath + "（版本 " + $displayVersion + "，" + $target.Variant + "）") -ForegroundColor Green
    }
    Remove-Item Env:\JY_BUILD_VARIANT -ErrorAction SilentlyContinue
    Remove-Item Env:\JY_BUILD_NAME -ErrorAction SilentlyContinue

    # 早期构建写的是不带版本号的固定名，留着会和带版本号的产物混在一起，一并清掉。
    foreach ($stale in @("JiYuAttackNext", "JiYuAttackNext_Debug")) {
        $stalePath = Join-Path $outputRoot ($stale + ".exe")
        if (-not (Test-Path -LiteralPath $stalePath -PathType Leaf)) {
            continue
        }
        try {
            Remove-Item -LiteralPath $stalePath -Force
        } catch {
            Write-Warning ("旧产物 " + $stale + ".exe 正在运行，无法移除；新版本已构建完成。")
        }
    }

    $legacyPath = Join-Path $outputRoot "JiyuUdpTest.exe"
    if (Test-Path -LiteralPath $legacyPath -PathType Leaf) {
        try {
            Remove-Item -LiteralPath $legacyPath -Force
        } catch {
            Write-Warning "旧版 JiyuUdpTest.exe 正在运行，无法移除；新版本已构建完成。"
        }
    }
}
finally {
    Remove-Item Env:\JY_BUILD_VARIANT -ErrorAction SilentlyContinue
    Remove-Item Env:\JY_BUILD_NAME -ErrorAction SilentlyContinue
    Pop-Location
}
