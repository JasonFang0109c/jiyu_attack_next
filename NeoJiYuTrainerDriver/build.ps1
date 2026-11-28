#requires -Version 5.1
<#
.SYNOPSIS
    在 Windows 容器内构建可选内核驱动。

.DESCRIPTION
    对应 JiYuTrainer 上游的 JiYuTrainerDriver 工程。宿主机不安装 WDK 与
    MSVC:源码通过容器的 C:\src 绑定装入容器,再调用容器内的 build.bat
    编译,产物写入 build/native/driver/。

.PARAMETER Container
    Windows 容器名,默认 jiyu-native。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\NeoJiYuTrainerDriver\build.ps1
#>

param(
    [string]$Container = "jiyu-native"
)

$ErrorActionPreference = "Stop"
$work = "C:\work\driver"
$out = "C:\src\build\native\driver"

$running = docker inspect -f "{{.State.Running}}" $Container 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
    throw "容器 $Container 未运行,请先 docker start $Container"
}

docker exec $Container cmd /c "if exist $work rmdir /s /q $work"
docker exec $Container cmd /c "xcopy /E /I /Y C:\src\NeoJiYuTrainerDriver $work >nul"
if ($LASTEXITCODE -ne 0) {
    throw "驱动程序源码复制失败:$LASTEXITCODE"
}
docker exec $Container cmd /c "call C:\src\NeoJiYuTrainerDriver\build.bat $work $out"
if ($LASTEXITCODE -ne 0) {
    throw "驱动程序构建失败:$LASTEXITCODE"
}

Write-Host "构建产物:build\native\driver"
