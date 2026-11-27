param(
    [string]$Container = "jiyu-native"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$work = "C:\work\driver"
$out = "C:\src\build\native\driver"

$running = docker inspect -f "{{.State.Running}}" $Container 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
    throw "容器 $Container 未运行，请先 docker start $Container"
}

docker exec $Container cmd /c "if exist $work rmdir /s /q $work"
docker exec $Container cmd /c "xcopy /E /I /Y C:\src\pack\native\driver $work >nul"
if ($LASTEXITCODE -ne 0) {
    throw "驱动程序源码复制失败：$LASTEXITCODE"
}
docker exec $Container cmd /c "call C:\src\pack\native\driver\build.bat $work $out"
if ($LASTEXITCODE -ne 0) {
    throw "驱动程序构建失败：$LASTEXITCODE"
}

Write-Host "构建产物：build\native\driver"
