$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "未找到虚拟环境。请先在项目根目录执行：py -3.13 -m venv .venv"
}

Set-Location -LiteralPath $projectRoot
& $pythonExe -X utf8 ".\gui.py"
exit $LASTEXITCODE
