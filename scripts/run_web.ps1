<#
.SYNOPSIS
    CADMVP Windows Web Server
.EXAMPLE
    .\scripts\run_web.ps1
    .\scripts\run_web.ps1 -Port 8080
#>

param(
    [int]$Port = 8010,
    [string]$BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$webServer = Join-Path $ProjectRoot "scripts\web_server.py"

if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}

if (-not (Test-Path $webServer)) {
    Write-Host "[ERROR] scripts/web_server.py not found" -ForegroundColor Red
    exit 1
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  CADMVP Web Server" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Python: $venvPython"
Write-Host "URL: http://${BindHost}:${Port}"
Write-Host ""
Write-Host "Press Ctrl+C to stop."
Write-Host ""

& $venvPython $webServer --host $BindHost --port $Port
