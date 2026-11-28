param(
    [string]$Container = "jiyu-native",
    [string]$Password = "JiyuGuardTest!"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$signing = Join-Path $repo "Build\Signing"
$driver = Join-Path $repo "NeoJiYuTrainer\Resources\Native\Driver\JiYuGuardDriver.sys"

if (-not (Test-Path -LiteralPath $driver)) {
    throw "找不到驱动文件：$driver"
}
New-Item -ItemType Directory -Force -Path $signing | Out-Null

$subject = "CN=JiYuGuard Test"
$certificate = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object { $_.Subject -eq $subject -and $_.HasPrivateKey } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1
if ($null -eq $certificate) {
    $certificate = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $subject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyUsage DigitalSignature `
        -KeyExportPolicy Exportable `
        -NotAfter (Get-Date).AddYears(2)
}
Write-Host "代码签名证书：$($certificate.Thumbprint)"

$securePassword = ConvertTo-SecureString -String $Password -Force -AsPlainText
$pfx = Join-Path $signing "JiYuGuardTest.pfx"
$cer = Join-Path $signing "JiYuGuardTest.cer"
Export-PfxCertificate -Cert $certificate -FilePath $pfx -Password $securePassword | Out-Null
Export-Certificate -Cert $certificate -FilePath $cer | Out-Null

# 让当前用户信任这张测试证书；目标机器若要加载驱动，需要把 cer 导入
# LocalMachine\Root 与 LocalMachine\TrustedPublisher（管理员操作）。
Import-Certificate -FilePath $cer -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
Import-Certificate -FilePath $cer -CertStoreLocation "Cert:\CurrentUser\TrustedPublisher" | Out-Null

$batch = Join-Path $signing "SignDriver.bat"
@"
@echo off
cd /d "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x86"
signtool.exe sign /fd SHA256 /f C:\src\Build\Signing\JiYuGuardTest.pfx /p $Password C:\src\NeoJiYuTrainer\Resources\Native\Driver\JiYuGuardDriver.sys
exit /b %ERRORLEVEL%
"@ | Set-Content -LiteralPath $batch -Encoding ASCII

$info = docker inspect -f "{{.State.Running}}" $Container 2>$null
if ($LASTEXITCODE -ne 0 -or $info.Trim() -ne "true") {
    docker start $Container | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "无法启动构建容器：$Container"
    }
}
docker exec $Container cmd /c "C:\src\Build\Signing\SignDriver.bat"
if ($LASTEXITCODE -ne 0) {
    throw "signtool 签名失败：$LASTEXITCODE"
}

$signature = Get-AuthenticodeSignature -LiteralPath $driver
Write-Host "签名状态：$($signature.Status)"
Write-Host "签名文件：$driver"
Write-Host "证书文件：$cer"
Write-Host "PFX 文件：$pfx"
Write-Host "提示：测试签名还需在目标机器以管理员执行 bcdedit /set Testsigning on 并重启，Secure Boot 必须关闭。"
