param(
    [string]$Container = "jiyu-native"
)
# 用已预装 MSVC/SDK 的 Windows 容器构建课堂防护 DLL；宿主机不安装编译工具。
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$work = "C:\work\guard"
$out = "C:\src\build\native\guard"

docker ps --format "{{.Names}}" | Select-String -Quiet "^$Container$" | Out-Null
if (-not $?) {
    throw "容器 $Container 未运行；请先按 docs/dev/BUILD.md 启动 Windows 构建容器"
}

$command = "if exist $work rmdir /s /q $work & xcopy /E /I /Y C:\src\pack\native\guard $work >nul & call C:\src\pack\native\guard\build.bat x64 $work $out & call C:\src\pack\native\guard\build.bat x86 $work $out"
docker exec $Container cmd /c $command
if ($LASTEXITCODE -ne 0) { throw "课堂防护 DLL 构建失败：$LASTEXITCODE" }
Write-Host "构建产物：build\native\guard"
