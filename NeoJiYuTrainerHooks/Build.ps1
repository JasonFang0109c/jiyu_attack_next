#requires -Version 5.1
<#
.SYNOPSIS
    在 Windows 容器内构建课堂防护 DLL 与自测夹具。

.DESCRIPTION
    对应 JiYuTrainer 上游的 JiYuTrainerHooks 工程。宿主机不安装 MSVC 与
    Windows SDK:源码通过容器的 C:\src 绑定装入容器,再调用容器内的
    Build.bat 分别编译 x64 与 x86,产物写入 Build/Native/Hooks/。

.PARAMETER Container
    Windows 容器名,默认 jiyu-native。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\NeoJiYuTrainerHooks\Build.ps1
#>

param(
    [string]$Container = "jiyu-native"
)

$ErrorActionPreference = "Stop"
$work = "C:\work\hooks"
$out = "C:\src\Build\Native\Hooks"

$running = docker inspect -f "{{.State.Running}}" $Container 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
    throw "容器 $Container 未运行,请先 docker start $Container"
}

docker exec $Container cmd /c "if exist $work rmdir /s /q $work"
docker exec $Container cmd /c "xcopy /E /I /Y C:\src\NeoJiYuTrainerHooks $work >nul"
if ($LASTEXITCODE -ne 0) {
    throw "课堂防护源码复制失败:$LASTEXITCODE"
}

docker exec $Container cmd /c "call C:\src\NeoJiYuTrainerHooks\Build.bat x64 $work $out"
if ($LASTEXITCODE -ne 0) {
    throw "课堂防护 x64 构建失败:$LASTEXITCODE"
}
docker exec $Container cmd /c "call C:\src\NeoJiYuTrainerHooks\Build.bat x86 $work $out"
if ($LASTEXITCODE -ne 0) {
    throw "课堂防护 x86 构建失败:$LASTEXITCODE"
}

Write-Host "构建产物:Build\Native\Hooks"
