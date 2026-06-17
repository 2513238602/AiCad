<#
.SYNOPSIS
    AiCad V2 reproducibility smoke test for Windows.
.DESCRIPTION
    Verifies the Python/CadQuery runtime, generates all four lip-gloss
    components, verifies committed showroom assets, optionally builds the
    frontend, and probes the local web API.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/smoke_v2.ps1
#>

param(
    [string]$EnvName = "AiCad",
    [string]$Python = "",
    [int]$Port = 8010,
    [switch]$SkipFrontendBuild,
    [switch]$SkipWebApi,
    [switch]$KeepServer
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$WebRoot = Join-Path $ProjectRoot "web"
$GenerateScript = Join-Path $ProjectRoot "scripts\generate.py"
$SelfTestScript = Join-Path $ProjectRoot "scripts\selftest_cadquery.py"
$WebServerScript = Join-Path $ProjectRoot "scripts\web_server.py"
$SmokeOut = Join-Path $ProjectRoot "artifacts\smoke_v2"
$BaseUrl = "http://127.0.0.1:$Port"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$script:PassCount = 0
$script:WarnCount = 0
$script:FailCount = 0

function Write-Check {
    param([string]$Label, [string]$Status, [string]$Detail = "")
    $color = switch ($Status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        default { "Cyan" }
    }
    if ($Status -eq "PASS") { $script:PassCount++ }
    elseif ($Status -eq "WARN") { $script:WarnCount++ }
    elseif ($Status -eq "FAIL") { $script:FailCount++ }
    Write-Host ("[{0}] {1}" -f $Status, $Label) -ForegroundColor $color
    if ($Detail) { Write-Host "      $Detail" -ForegroundColor DarkGray }
}

function Invoke-Check {
    param([string]$Label, [scriptblock]$Block)
    try {
        $detail = & $Block
        Write-Check $Label "PASS" $detail
    } catch {
        Write-Check $Label "FAIL" $_.Exception.Message
    }
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

function Resolve-Python {
    param([string]$Requested, [string]$Name)
    if ($Requested) {
        if (Test-Path $Requested) { return (Resolve-Path $Requested).Path }
        return $Requested
    }

    $Conda = Get-CondaCommand
    if ($Conda) {
        try {
            $raw = & $Conda env list --json 2>$null
            if ($LASTEXITCODE -eq 0 -and $raw) {
                $info = $raw | ConvertFrom-Json
                foreach ($envPath in $info.envs) {
                    if ((Split-Path $envPath -Leaf) -eq $Name) {
                        $p = Join-Path $envPath "python.exe"
                        if (Test-Path $p) { return $p }
                    }
                }
            }
        } catch { }
    }

    $candidates = @(
        "$env:USERPROFILE\.conda\envs\$Name\python.exe",
        "$env:USERPROFILE\miniconda3\envs\$Name\python.exe",
        "$env:USERPROFILE\anaconda3\envs\$Name\python.exe",
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return "python"
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

function Test-HttpJson {
    param([string]$Url)
    try {
        return Invoke-RestMethod -Uri $Url -TimeoutSec 5
    } catch {
        return $null
    }
}

function Resolve-OutputPath {
    param([string]$Value)
    if ([System.IO.Path]::IsPathRooted($Value)) { return $Value }
    return (Join-Path $ProjectRoot $Value)
}

Write-Host ""
Write-Host "AiCad V2 smoke test" -ForegroundColor Green
Write-Host "Project: $ProjectRoot"

$PythonExe = Resolve-Python -Requested $Python -Name $EnvName
Write-Host "Python: $PythonExe" -ForegroundColor DarkGray

Invoke-Check "Python 3.11 runtime" {
    $version = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($version | Out-String) }
    if (-not ($version -like "3.11*")) { throw "Expected Python 3.11.x, got $version" }
    $version
}

Invoke-Check "Core Python imports" {
    $code = "import cadquery as cq; from OCP.TopoDS import TopoDS_Shape; import numpy, cv2, PIL, requests, aiohttp; print('cadquery=' + cq.__version__)"
    $out = & $PythonExe -c $code 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($out | Out-String) }
    $out
}

Invoke-Check "CadQuery selftest" {
    $out = & $PythonExe $SelfTestScript 2>&1
    if ($LASTEXITCODE -ne 0) { throw (($out | Select-Object -Last 20) -join "`n") }
    "STEP export selftest passed"
}

Invoke-Check "Generate four CAD components" {
    New-Item -ItemType Directory -Path $SmokeOut -Force | Out-Null
    $items = @(
        @{ component = "bottle"; preset = "bottle_standard_5ml" },
        @{ component = "cap"; preset = "cap_18415_standard" },
        @{ component = "wiper"; preset = "wiper_standard_18" },
        @{ component = "wand"; preset = "wand_integrated_18" }
    )
    foreach ($item in $items) {
        $raw = & $PythonExe $GenerateScript --product lip_gloss --component $item.component --preset $item.preset --outroot $SmokeOut 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "$($item.component) generation failed:`n$($raw | Out-String)"
        }
        $json = ($raw | Out-String) | ConvertFrom-Json
        if (-not $json.ok) {
            throw "$($item.component) returned ok=false: $($json.error)"
        }
        foreach ($field in @("step", "stl", "svg")) {
            $p = Resolve-OutputPath $json.$field
            if (-not (Test-Path $p)) {
                throw "$($item.component) missing $field output: $p"
            }
        }
    }
    "bottle, cap, wiper, wand generated STEP/STL/SVG"
}

Invoke-Check "Committed showroom assets" {
    $assets = @(
        "web\public\assets\showroom-gallery\gallery_shell.glb",
        "web\public\assets\showroom-gallery\gallery_manifest.json",
        "web\public\assets\showroom-unreal\manifest.json",
        "web\public\assets\showroom-unreal\Display_Main_C.glb",
        "artifacts\showroom\empty_showroom.glb",
        "artifacts\showroom\manifest.json"
    )
    foreach ($rel in $assets) {
        $p = Join-Path $ProjectRoot $rel
        if (-not (Test-Path $p)) { throw "Missing asset: $rel" }
    }
    "showroom gallery/unreal GLB manifests are present"
}

if (-not $SkipFrontendBuild) {
    Invoke-Check "Frontend production build" {
        $Npm = Get-NpmCommand
        if (-not $Npm) { throw "npm not found" }
        Push-Location $WebRoot
        try {
            $oldErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $out = & $Npm run build 2>&1
            $code = $LASTEXITCODE
            $ErrorActionPreference = $oldErrorActionPreference
            if ($code -ne 0) { throw (($out | Select-Object -Last 30) -join "`n") }
        } finally {
            if ($oldErrorActionPreference) {
                $ErrorActionPreference = $oldErrorActionPreference
            }
            Pop-Location
        }
        "npm run build passed"
    }
}

if (-not $SkipWebApi) {
    $serverJob = $null
    $serverWasRunning = $false
    try {
        $schema = Test-HttpJson "$BaseUrl/api/schema"
        if ($schema) {
            $serverWasRunning = $true
            Write-Check "Web server already running" "WARN" $BaseUrl
        } else {
            $serverJob = Start-Job -ScriptBlock {
                param($Root, $PythonExe, $ServerScript, $Port)
                Set-Location $Root
                & $PythonExe $ServerScript --host 127.0.0.1 --port $Port
            } -ArgumentList $ProjectRoot, $PythonExe, $WebServerScript, $Port

            $deadline = (Get-Date).AddSeconds(45)
            do {
                Start-Sleep -Milliseconds 800
                $schema = Test-HttpJson "$BaseUrl/api/schema"
            } while (-not $schema -and (Get-Date) -lt $deadline)
        }

        if (-not $schema) {
            throw "Server did not respond at $BaseUrl/api/schema"
        }
        if (-not $schema.products -or $schema.products.Count -lt 1) {
            throw "Schema response does not contain products"
        }
        Write-Check "Web API /api/schema" "PASS" "products=$($schema.products.Count)"

        $body = @{
            product = "lip_gloss"
            component = "bottle"
            preset_id = "bottle_standard_5ml"
            params = @{}
            title = "V2 smoke API bottle"
        } | ConvertTo-Json -Depth 8
        $res = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/generate" -ContentType "application/json" -Body $body -TimeoutSec 120
        if (-not $res.ok) {
            throw "/api/generate returned ok=false: $($res.error)"
        }
        Write-Check "Web API /api/generate" "PASS" "bottle generated"
    } catch {
        Write-Check "Web API smoke" "FAIL" $_.Exception.Message
    } finally {
        if ($serverJob -and -not $KeepServer -and -not $serverWasRunning) {
            Stop-Job $serverJob -ErrorAction SilentlyContinue | Out-Null
            Remove-Job $serverJob -ErrorAction SilentlyContinue | Out-Null
        }
    }
}

$Blender = Get-Command blender -ErrorAction SilentlyContinue
if ($Blender) {
    Write-Check "Blender CLI optional check" "PASS" $Blender.Source
} else {
    Write-Check "Blender CLI optional check" "WARN" "Not required to view committed showroom assets; required only to rebuild Blender-generated assets."
}

if (-not $env:GLM_API_KEY) {
    Write-Check "GLM_API_KEY optional check" "WARN" "VLM image analysis is disabled until .env or the process environment provides GLM_API_KEY."
} else {
    Write-Check "GLM_API_KEY optional check" "PASS" "Configured"
}

Write-Host ""
Write-Host "Summary: $script:PassCount passed, $script:WarnCount warnings, $script:FailCount failed"

if ($script:FailCount -gt 0) {
    exit 1
}
exit 0
