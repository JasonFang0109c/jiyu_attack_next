#requires -Version 5.1
<#
.SYNOPSIS
    在 Windows 容器内构建可选内核驱动。

.DESCRIPTION
    对应 JiYuTrainer 上游的 JiYuTrainerDriver 工程。宿主机不安装 WDK 与
    MSVC:源码通过容器的 C:\src 绑定装入容器,再调用容器内的 Build.bat
    编译,产物写入 Build/Native/Driver/。

.PARAMETER Container
    Windows 容器名,默认 jiyu-native。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\NeoJiYuTrainerDriver\Build.ps1
#>

param(
    [string]$Container = "jiyu-native",
    [switch]$SkipSign
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$work = "C:\work\driver"
$out = "C:\src\Build\Native\Driver"

$running = docker inspect -f "{{.State.Running}}" $Container 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
    throw "容器 $Container 未运行,请先 docker start $Container"
}

docker exec $Container cmd /c "if exist $work rmdir /s /q $work"
docker exec $Container cmd /c "xcopy /E /I /Y C:\src\NeoJiYuTrainerDriver $work >nul"
if ($LASTEXITCODE -ne 0) {
    throw "驱动程序源码复制失败:$LASTEXITCODE"
}
docker exec $Container cmd /c "call C:\src\NeoJiYuTrainerDriver\Build.bat $work $out"
if ($LASTEXITCODE -ne 0) {
    throw "驱动程序构建失败:$LASTEXITCODE"
}

$built = Join-Path $repo "Build\Native\Driver\JiYuGuardDriver.sys"
$target = Join-Path $repo "NeoJiYuTrainer\Resources\Native\Driver\JiYuGuardDriver.sys"
if (-not (Test-Path -LiteralPath $built)) {
    throw "找不到构建产物：$built"
}

Copy-Item -LiteralPath $built -Destination $target -Force
Write-Host "已更新打包用驱动：$target"

if ($SkipSign) {
    Write-Host "已跳过签名（-SkipSign）"
    return
}

& (Join-Path $repo "Pack\SignDriver.ps1") -Container $Container
if ($LASTEXITCODE -ne 0) {
    throw "驱动签名失败：$LASTEXITCODE"
}

$signature = Get-AuthenticodeSignature -LiteralPath $target
if ($signature.Status -ne "Valid") {
    throw "驱动签名状态不是 Valid：$($signature.Status)"
}
Write-Host "驱动已签名并更新到 Resources（$($signature.SignerCertificate.Subject)）"
