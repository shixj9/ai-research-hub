param(
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$certificatePath = Join-Path $projectRoot "backend\certs\localhost.pem"
$privateKeyPath = Join-Path $projectRoot "backend\certs\localhost-key.pem"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project virtual environment not found. Run 'uv sync' in the project root first."
}

if (-not (Test-Path -LiteralPath $certificatePath) -or
    -not (Test-Path -LiteralPath $privateKeyPath)) {
    & (Join-Path $PSScriptRoot "generate_dev_cert.ps1")
}

$uvicornArguments = @(
    "-m", "uvicorn",
    "backend.app.main:app",
    "--host", "127.0.0.1",
    "--port", "8443",
    "--ssl-certfile", $certificatePath,
    "--ssl-keyfile", $privateKeyPath
)

if (-not $NoReload) {
    $uvicornArguments += "--reload"
}

Set-Location $projectRoot
Write-Host "Starting AI Research Hub API at https://localhost:8443"
Write-Host "Swagger documentation: https://localhost:8443/docs"
& $pythonPath @uvicornArguments

