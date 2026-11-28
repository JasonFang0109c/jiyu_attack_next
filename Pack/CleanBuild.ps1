[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
if (
    -not (Test-Path -LiteralPath (Join-Path $root "Pack/Build.ps1") -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $root "NeoJiYuTrainer") -PathType Container)
) {
    throw "ProjectRoot 必须指向包含 Pack/Build.ps1 与 NeoJiYuTrainer/ 的项目根目录。"
}
$outputRoot = Join-Path $root "Output"

function Remove-CleanupTarget {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [Parameter(Mandatory)]
        [string]$LiteralPath
    )

    if (-not (Test-Path -LiteralPath $LiteralPath)) {
        return
    }
    if ($PSCmdlet.ShouldProcess($LiteralPath, "remove build residue")) {
        Remove-Item -LiteralPath $LiteralPath -Recurse -Force
        Write-Host ("Cleaned: " + $LiteralPath)
    }
}

# Check old executables before removing them so a running build cannot be deleted.
if (Test-Path -LiteralPath $outputRoot -PathType Container) {
    $oldExecutables = @(
        Get-ChildItem -LiteralPath $outputRoot -File -Filter "NeoJiYuTrainer*.exe"
    )
    foreach ($executable in $oldExecutables) {
        $running = $false
        foreach ($process in @(Get-Process -ErrorAction SilentlyContinue)) {
            try {
                if ([string]::Equals(
                        $process.Path,
                        $executable.FullName,
                        [System.StringComparison]::OrdinalIgnoreCase
                    )) {
                    $running = $true
                    break
                }
            } catch {
                # Some system processes deny access to Path; they are skipped.
            }
        }
        if ($running) {
            throw ("Close the running executable first: " + $executable.FullName)
        }
        Remove-CleanupTarget -LiteralPath $executable.FullName
    }
}

# Remove only reproducible PyInstaller work directories.
foreach ($relativePath in @(
    "Build/Release",
    "Build/Debug",
    "Build/Assets"
)) {
    Remove-CleanupTarget -LiteralPath (Join-Path $root $relativePath)
}

# Remove logs while preserving settings.json and all other user data.
foreach ($dataDirectory in @(
    (Join-Path $root "Data"),
    (Join-Path $outputRoot "Data")
)) {
    foreach ($logName in @("cli.log", "runtime.log")) {
        Remove-CleanupTarget -LiteralPath (Join-Path $dataDirectory $logName)
    }
}

# Remove common tool caches without traversing .venv or user data directories.
foreach ($relativePath in @(
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".coverage",
    "htmlcov"
)) {
    Remove-CleanupTarget -LiteralPath (Join-Path $root $relativePath)
}
foreach ($sourceDirectory in @("NeoJiYuTrainer", "Pack", "Scripts", "Tests")) {
    $sourceRoot = Join-Path $root $sourceDirectory
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
        continue
    }
    Get-ChildItem -LiteralPath $sourceRoot -Directory -Filter "__pycache__" -Recurse -Force |
        ForEach-Object { Remove-CleanupTarget -LiteralPath $_.FullName }
}

Write-Host "Build cleanup completed; settings.json and user data were preserved." -ForegroundColor Green
