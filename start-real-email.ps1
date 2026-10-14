[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

Write-Host "=========================================" -ForegroundColor Green
Write-Host "  NIDS startup with real QQ email" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Use a QQ Mail SMTP authorization code, not your QQ login password." -ForegroundColor Yellow
Write-Host ""

$smtpUser = Read-Host "Sender QQ email, for example 123456@qq.com"
$smtpPasswordSecure = Read-Host "SMTP authorization code" -AsSecureString
$smtpPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($smtpPasswordSecure)
)

$env:NIDS_SMTP_HOST = "smtp.qq.com"
$env:NIDS_SMTP_PORT = "587"
$env:NIDS_SMTP_TLS = "1"
$env:NIDS_SMTP_USER = $smtpUser
$env:NIDS_SMTP_PASSWORD = $smtpPassword
$env:NIDS_SMTP_FROM = $smtpUser
$env:NIDS_DEFAULT_EMAIL = Read-Host "Recipient administrator email"

.\start.ps1
