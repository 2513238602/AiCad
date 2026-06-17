<#
.SYNOPSIS
    CADMVP Windows 入口脚本
.EXAMPLE
    .\scripts\run.ps1 cap cap_full_detail_demo
#>

param(
    [string]$Component = "cap",
    [string]$Preset = "cap_full_detail_demo",
    [string]$ParamsJson = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$generateScript = Join-Path $ProjectRoot "scripts\generate.py"

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

if (-not (Test-Path $generateScript)) {
    Write-Host "[ERROR] scripts/generate.py not found" -ForegroundColor Red
    exit 1
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  CADMVP Generate" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Python: $venvPython"
Write-Host "Component: $Component"
Write-Host "Preset: $Preset"
Write-Host ""

if ($ParamsJson -and $ParamsJson.Trim() -ne "") {
    & $venvPython $generateScript --product lip_gloss --component $Component --preset $Preset --outroot "artifacts/cli" --params $ParamsJson
} else {
    & $venvPython $generateScript --product lip_gloss --component $Component --preset $Preset --outroot "artifacts/cli"
}

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host ""
    Write-Host "[OK] Generation completed." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[FAIL] Generation failed with exit code $exitCode" -ForegroundColor Red
}

exit $exitCode
