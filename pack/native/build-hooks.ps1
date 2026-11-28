param(
    [string]$Container = "jiyu-native"
)

$ErrorActionPreference = "Stop"
$work = "C:\work\hooks"
$out = "C:\src\build\native\hooks"

$running = docker inspect -f "{{.State.Running}}" $Container 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
    throw "容器 $Container 未运行，请先 docker start $Container"
}

docker exec $Container cmd /c "if exist $work rmdir /s /q $work"
docker exec $Container cmd /c "xcopy /E /I /Y C:\src\pack\native\hooks $work >nul"
if ($LASTEXITCODE -ne 0) {
    throw "课堂防护源码复制失败：$LASTEXITCODE"
}

docker exec $Container cmd /c "call C:\src\pack\native\hooks\build.bat x64 $work $out"
if ($LASTEXITCODE -ne 0) {
    throw "课堂防护 x64 构建失败：$LASTEXITCODE"
}
docker exec $Container cmd /c "call C:\src\pack\native\hooks\build.bat x86 $work $out"
if ($LASTEXITCODE -ne 0) {
    throw "课堂防护 x86 构建失败：$LASTEXITCODE"
}

Write-Host "构建产物：build\native\hooks"
