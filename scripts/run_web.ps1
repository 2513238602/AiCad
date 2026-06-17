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

function Resolve-Python {
    param([string]$EnvName = "AiCad")

    $conda = Get-Command conda.exe -ErrorAction SilentlyContinue
    if (-not $conda) { $conda = Get-Command conda -ErrorAction SilentlyContinue }
    if ($conda) {
        try {
            $raw = & $conda.Source env list --json 2>$null
            if ($LASTEXITCODE -eq 0 -and $raw) {
                $info = $raw | ConvertFrom-Json
                foreach ($envPath in $info.envs) {
                    if ((Split-Path $envPath -Leaf) -eq $EnvName) {
                        $p = Join-Path $envPath "python.exe"
                        if (Test-Path $p) { return $p }
                    }
                }
            }
        } catch { }
    }

    if (Test-Path $venvPython) { return $venvPython }
    return "python"
}

$venvPython = Resolve-Python

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
