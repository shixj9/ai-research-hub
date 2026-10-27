param(
    [int]$ValidDays = 365
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$certDirectory = Join-Path $projectRoot "backend\certs"
$certificatePath = Join-Path $certDirectory "localhost.pem"
$privateKeyPath = Join-Path $certDirectory "localhost-key.pem"

$openSslCommand = Get-Command openssl -ErrorAction SilentlyContinue
$openSslCandidates = @(
    if ($openSslCommand) { $openSslCommand.Source },
    "D:\software\Git\usr\bin\openssl.exe",
    "D:\software\Git\mingw64\bin\openssl.exe",
    "C:\Program Files\Git\usr\bin\openssl.exe",
    "C:\Program Files\Git\mingw64\bin\openssl.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if (-not $openSslCandidates) {
    throw "OpenSSL was not found. Install Git for Windows or OpenSSL, then retry."
}

$openSslPath = $openSslCandidates[0]
New-Item -ItemType Directory -Force -Path $certDirectory | Out-Null

& $openSslPath req `
    -x509 `
    -newkey rsa:2048 `
    -sha256 `
    -nodes `
    -keyout $privateKeyPath `
    -out $certificatePath `
    -days $ValidDays `
    -subj "/CN=localhost" `
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1"

if ($LASTEXITCODE -ne 0) {
    throw "OpenSSL failed to generate the local HTTPS certificate."
}

Write-Host "Development certificate created: $certificatePath"
Write-Host "Private key created: $privateKeyPath"
Write-Host "These files are for local development only and are ignored by Git."

