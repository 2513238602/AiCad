<#
.SYNOPSIS
    Bootstrap AiCad V2 on a fresh Windows machine.
.DESCRIPTION
    Creates/updates the Conda environment from environment.yml, installs
    frontend dependencies from package-lock.json, builds the Vue frontend,
    creates .env from .env.example when missing, and runs the V2 smoke test.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/bootstrap_windows.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/bootstrap_windows.ps1 -UpdateEnv -SkipSmoke
#>

param(
    [string]$EnvName = "AiCad",
    [switch]$UpdateEnv,
    [switch]$SkipConda,
    [switch]$SkipFrontend,
    [switch]$SkipBuild,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$WebRoot = Join-Path $ProjectRoot "web"
$EnvironmentFile = Join-Path $ProjectRoot "environment.yml"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$EnvFile = Join-Path $ProjectRoot ".env"
$SmokeScript = Join-Path $ProjectRoot "scripts\smoke_v2.ps1"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

function Write-Title {
    param([string]$Text)
    Write-Host ""
    Write-Host "== $Text ==" -ForegroundColor Cyan
}

function Get-CondaCommand {
    $cmd = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniforge3\Scripts\conda.exe",
        "C:\ProgramData\miniconda3\Scripts\conda.exe",
        "C:\ProgramData\anaconda3\Scripts\conda.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Get-NpmCommand {
    $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command npm.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Test-CondaEnv {
    param([string]$Conda, [string]$Name)
    $raw = & $Conda env list --json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $false }
    $info = $raw | ConvertFrom-Json
    foreach ($envPath in $info.envs) {
        if ((Split-Path $envPath -Leaf) -eq $Name) { return $true }
    }
    return $false
}

Write-Host ""
Write-Host "AiCad V2 Windows bootstrap" -ForegroundColor Green
Write-Host "Project: $ProjectRoot"

if (-not (Test-Path $EnvironmentFile)) {
    throw "environment.yml not found: $EnvironmentFile"
}

if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Host "Created .env from .env.example" -ForegroundColor DarkGray
}

if (-not $SkipConda) {
    Write-Title "Conda environment"
    $Conda = Get-CondaCommand
    if (-not $Conda) {
        throw "Conda was not found. Install Miniconda or Miniforge, then rerun this script."
    }
    Write-Host "Conda: $Conda"

    $exists = Test-CondaEnv -Conda $Conda -Name $EnvName
    if (-not $exists) {
        Write-Host "Creating Conda environment '$EnvName' from environment.yml..."
        & $Conda env create -n $EnvName -f $EnvironmentFile
        if ($LASTEXITCODE -ne 0) { throw "conda env create failed" }
    } elseif ($UpdateEnv) {
        Write-Host "Updating Conda environment '$EnvName' from environment.yml..."
        & $Conda env update -n $EnvName -f $EnvironmentFile --prune
        if ($LASTEXITCODE -ne 0) { throw "conda env update failed" }
    } else {
        Write-Host "Conda environment '$EnvName' already exists. Use -UpdateEnv to refresh it."
    }
}

if (-not $SkipFrontend) {
    Write-Title "Frontend dependencies"
    $Npm = Get-NpmCommand
    if (-not $Npm) {
        throw "npm was not found. Install Node.js 20+, or use the nodejs package from the Conda env."
    }
    Write-Host "npm: $Npm"

    Push-Location $WebRoot
    try {
        $oldErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        if (Test-Path (Join-Path $WebRoot "package-lock.json")) {
            & $Npm ci
        } else {
            & $Npm install
        }
        $installCode = $LASTEXITCODE
        $ErrorActionPreference = $oldErrorActionPreference
        if ($installCode -ne 0) { throw "npm dependency install failed" }

        if (-not $SkipBuild) {
            $oldErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            & $Npm run build
            $buildCode = $LASTEXITCODE
            $ErrorActionPreference = $oldErrorActionPreference
            if ($buildCode -ne 0) { throw "npm build failed" }
        }
    } finally {
        if ($oldErrorActionPreference) {
            $ErrorActionPreference = $oldErrorActionPreference
        }
        Pop-Location
    }
}

if (-not $SkipSmoke) {
    Write-Title "Smoke test"
    if (-not (Test-Path $SmokeScript)) {
        throw "Smoke script not found: $SmokeScript"
    }
    & $SmokeScript -EnvName $EnvName -SkipFrontendBuild:$SkipBuild
    if ($LASTEXITCODE -ne 0) { throw "V2 smoke test failed" }
}

Write-Host ""
Write-Host "AiCad V2 bootstrap finished." -ForegroundColor Green
Write-Host "Start the app with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/start.ps1"
