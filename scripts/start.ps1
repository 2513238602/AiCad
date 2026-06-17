<#
.SYNOPSIS
    AiCad one-click launcher: env check + cache clean + frontend build + server start
.EXAMPLE
    .\scripts\start.ps1
    .\scripts\start.ps1 -Port 8080
    .\scripts\start.ps1 -SkipBuild
    .\scripts\start.ps1 -ForceBuild
#>

param(
    [int]$Port = 8010,
    [string]$BindHost = "127.0.0.1",
    [switch]$SkipBuild,
    [switch]$ForceBuild,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$WebRoot = Join-Path $ProjectRoot "web"
$DistRoot = Join-Path $WebRoot "dist"
$SrcRoot = Join-Path $ProjectRoot "src"
$WebServer = Join-Path (Join-Path $ProjectRoot "scripts") "web_server.py"

# Force UTF-8 console output
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$passCount = 0
$failCount = 0
$warnCount = 0

function Write-Check {
    param([string]$Label, [string]$Status, [string]$Detail = "")
    switch ($Status) {
        "PASS" {
            Write-Host "  [PASS] " -ForegroundColor Green -NoNewline
            $script:passCount++
        }
        "FAIL" {
            Write-Host "  [FAIL] " -ForegroundColor Red -NoNewline
            $script:failCount++
        }
        "WARN" {
            Write-Host "  [WARN] " -ForegroundColor Yellow -NoNewline
            $script:warnCount++
        }
        "INFO" {
            Write-Host "  [INFO] " -ForegroundColor Cyan -NoNewline
        }
        "SKIP" {
            Write-Host "  [SKIP] " -ForegroundColor DarkGray -NoNewline
        }
    }
    Write-Host $Label -NoNewline
    if ($Detail) {
        Write-Host " - $Detail" -ForegroundColor DarkGray
    } else {
        Write-Host ""
    }
}

function Resolve-Npm {
    $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command npm.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

# ============================================================
#  Banner
# ============================================================
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host "    AiCad v2.0 Launcher" -ForegroundColor Cyan
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
#  Step 1: Clean caches
# ============================================================
Write-Host "  [1/7] Cache Cleanup" -ForegroundColor White
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray

# Python __pycache__ (prevents stale bytecode)
$pycacheDirs = Get-ChildItem -Path $SrcRoot -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue
if ($pycacheDirs -and $pycacheDirs.Count -gt 0) {
    $pycacheDirs | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Check "Python __pycache__ cleared" "PASS" "$($pycacheDirs.Count) dirs in src/"
} else {
    Write-Check "No __pycache__ found" "PASS"
}

# Also clean scripts/ and tests/ pycache
$extraPycache = @("scripts", "tests") | ForEach-Object {
    $d = Join-Path $ProjectRoot $_
    if (Test-Path $d) {
        Get-ChildItem -Path $d -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue
    }
} | Where-Object { $_ -ne $null }
if ($extraPycache -and @($extraPycache).Count -gt 0) {
    $extraPycache | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Check "Extra __pycache__ cleared" "PASS" "scripts/ + tests/"
}

# .pyc in root
$rootPyc = Get-ChildItem -Path $ProjectRoot -Filter "*.pyc" -File -ErrorAction SilentlyContinue
if ($rootPyc -and $rootPyc.Count -gt 0) {
    $rootPyc | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Check "Stale .pyc files removed" "PASS" "$($rootPyc.Count) files"
}

# .pytest_cache
$pytestCache = Join-Path $ProjectRoot ".pytest_cache"
if (Test-Path $pytestCache) {
    Remove-Item -Path $pytestCache -Recurse -Force -ErrorAction SilentlyContinue
    Write-Check ".pytest_cache cleared" "PASS"
}

Write-Host ""

# ============================================================
#  Step 2: Conda activation + Python
# ============================================================
Write-Host "  [2/7] Python / Conda" -ForegroundColor White
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray

$Python = $null
$condaActivated = $false

# --- Try to activate conda environment "AiCad" ---
$condaHookPaths = @(
    "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1",
    "$env:USERPROFILE\anaconda3\shell\condabin\conda-hook.ps1",
    "$env:USERPROFILE\miniforge3\shell\condabin\conda-hook.ps1",
    "C:\ProgramData\miniconda3\shell\condabin\conda-hook.ps1",
    "C:\ProgramData\anaconda3\shell\condabin\conda-hook.ps1"
)

if ($env:CONDA_EXE) {
    $condaRoot = Split-Path -Parent (Split-Path -Parent $env:CONDA_EXE)
    $hookFromExe = Join-Path $condaRoot "shell\condabin\conda-hook.ps1"
    $condaHookPaths = @($hookFromExe) + $condaHookPaths
}

$condaHook = $null
foreach ($h in $condaHookPaths) {
    if (Test-Path $h) {
        $condaHook = $h
        break
    }
}

if ($condaHook) {
    try {
        . $condaHook
        conda activate AiCad 2>$null
        if ($LASTEXITCODE -eq 0 -or $env:CONDA_DEFAULT_ENV -eq "AiCad") {
            $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
            if ($Python) {
                $condaActivated = $true
                Write-Check "Conda activate AiCad" "PASS"
            }
        }
    } catch {
        # activation failed, fall through
    }
}

# Fallback: direct path to conda env python
if (-not $Python) {
    $condaDirs = @(
        "$env:USERPROFILE\.conda\envs\AiCad",
        "$env:USERPROFILE\miniconda3\envs\AiCad",
        "$env:USERPROFILE\anaconda3\envs\AiCad"
    )
    foreach ($d in $condaDirs) {
        $p = Join-Path $d "python.exe"
        if (Test-Path $p) {
            $Python = $p
            Write-Check "Conda env (direct path)" "PASS" $p
            break
        }
    }
}

# Fallback: project .venv
if (-not $Python) {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $Python = $venvPython
        Write-Check "Venv" "PASS" $venvPython
    }
}

# Fallback: system python
if (-not $Python) {
    try {
        $sysPython = (Get-Command python -ErrorAction SilentlyContinue).Source
        if ($sysPython) {
            $Python = $sysPython
            Write-Check "System Python" "WARN" $sysPython
        }
    } catch { }
}

if (-not $Python) {
    Write-Check "Python not found" "FAIL"
    Write-Host ""
    Write-Host "  Install Python + CadQuery first:" -ForegroundColor Yellow
    Write-Host "    conda create -n AiCad python=3.11" -ForegroundColor Yellow
    Write-Host "    conda activate AiCad" -ForegroundColor Yellow
    Write-Host "    pip install cadquery" -ForegroundColor Yellow
    exit 1
}

# Python version
$pyVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
if ($pyVersion) {
    Write-Check "Python $pyVersion" "PASS"
}

Write-Host ""

# ============================================================
#  Step 3: Core dependencies
# ============================================================
Write-Host "  [3/7] Core Dependencies" -ForegroundColor White
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray

# CadQuery
$cqOk = $false
$cqVersion = & $Python -c "import cadquery as cq; print(cq.__version__)" 2>$null
if ($LASTEXITCODE -eq 0 -and $cqVersion) {
    Write-Check "CadQuery $cqVersion" "PASS"
    $cqOk = $true
} else {
    Write-Check "CadQuery not installed" "FAIL" "pip install cadquery"
}

# OCP
$ocpOk = & $Python -c "from OCP.TopoDS import TopoDS_Shape; print('ok')" 2>$null
if ($LASTEXITCODE -eq 0 -and $ocpOk -eq "ok") {
    Write-Check "OCP (OpenCascade)" "PASS"
} else {
    Write-Check "OCP import failed" "WARN"
}

# Project modules
$srcOk = & $Python -c "import sys; sys.path.insert(0,'$($ProjectRoot -replace '\\','/')/src'); from products.lip_gloss.components.registry import schema; print('ok')" 2>$null
if ($LASTEXITCODE -eq 0 -and $srcOk -eq "ok") {
    Write-Check "Project modules" "PASS"
} else {
    Write-Check "Project modules import failed" "FAIL"
}

if (-not $cqOk) {
    Write-Host ""
    Write-Host "  CadQuery is required. Install:" -ForegroundColor Red
    Write-Host "    conda install -c cadquery -c conda-forge cadquery" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# ============================================================
#  Step 4: Node.js / npm
# ============================================================
Write-Host "  [4/7] Node.js / npm" -ForegroundColor White
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray

$npmOk = $false

try {
    $nodeVersion = & node --version 2>$null
    if ($LASTEXITCODE -eq 0 -and $nodeVersion) {
        Write-Check "Node.js $nodeVersion" "PASS"
    } else {
        Write-Check "Node.js not found" "FAIL"
    }
} catch {
    Write-Check "Node.js not found" "FAIL"
}

try {
    $Npm = Resolve-Npm
    if (-not $Npm) {
        Write-Check "npm not available" "FAIL"
    } else {
        $npmVersion = & $Npm --version 2>$null
    }
    if ($LASTEXITCODE -eq 0 -and $npmVersion) {
        Write-Check "npm $npmVersion" "PASS"
        $npmOk = $true
    } else {
        Write-Check "npm not available" "FAIL"
    }
} catch {
    Write-Check "npm not available" "FAIL"
}

Write-Host ""

# ============================================================
#  Step 5: Frontend dependencies
# ============================================================
Write-Host "  [5/7] Frontend Dependencies" -ForegroundColor White
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray

$nodeModules = Join-Path $WebRoot "node_modules"
$needInstall = $false

if (Test-Path $nodeModules) {
    $pkgJson = Join-Path $WebRoot "package.json"
    $pkgTime = (Get-Item $pkgJson).LastWriteTime
    $nmTime = (Get-Item $nodeModules).LastWriteTime
    if ($pkgTime -gt $nmTime) {
        Write-Check "node_modules outdated" "WARN" "package.json is newer"
        $needInstall = $true
    } else {
        Write-Check "node_modules ready" "PASS"
    }
} else {
    Write-Check "node_modules missing" "WARN"
    $needInstall = $true
}

if ($needInstall -and $npmOk) {
    Write-Host ""
    Write-Host "    Running npm install..." -ForegroundColor Cyan
    Push-Location $WebRoot
    $ErrorActionPreference = "Continue"
    try {
        & $Npm install 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Check "npm install done" "PASS"
        } else {
            Write-Check "npm install failed" "FAIL" "exit code: $LASTEXITCODE"
        }
    } finally {
        $ErrorActionPreference = "Stop"
        Pop-Location
    }
} elseif ($needInstall -and -not $npmOk) {
    Write-Check "Cannot install (npm unavailable)" "FAIL"
}

Write-Host ""

# ============================================================
#  Step 6: Frontend build (with stale dist cleanup)
# ============================================================
Write-Host "  [6/7] Frontend Build" -ForegroundColor White
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray

$needBuild = $false
$distIndex = Join-Path $DistRoot "index.html"

if ($SkipBuild) {
    Write-Check "Build skipped" "SKIP" "-SkipBuild"
} elseif ($ForceBuild) {
    # Force: delete old dist entirely
    if (Test-Path $DistRoot) {
        Remove-Item -Path $DistRoot -Recurse -Force -ErrorAction SilentlyContinue
        Write-Check "Old dist/ deleted" "INFO" "force clean rebuild"
    }
    $needBuild = $true
    Write-Check "Force rebuild" "INFO" "-ForceBuild"
} elseif (-not (Test-Path $distIndex)) {
    $needBuild = $true
    Write-Check "dist/ not found" "WARN" "build required"
} else {
    # Check if any source file is newer than dist
    $distTime = (Get-Item $distIndex).LastWriteTime
    $srcFiles = Get-ChildItem -Path (Join-Path $WebRoot "src") -Recurse -File |
                Where-Object { $_.LastWriteTime -gt $distTime } |
                Select-Object -First 1
    # Also check config files
    $configFiles = @("vite.config.ts", "tsconfig.json", "tsconfig.app.json", "package.json") | ForEach-Object {
        $cf = Join-Path $WebRoot $_
        if ((Test-Path $cf) -and (Get-Item $cf).LastWriteTime -gt $distTime) { $cf }
    }
    if ($srcFiles -or $configFiles) {
        $needBuild = $true
        # Delete stale dist to ensure clean build
        Remove-Item -Path $DistRoot -Recurse -Force -ErrorAction SilentlyContinue
        Write-Check "Source updated, stale dist/ cleaned" "WARN" "rebuilding"
    } else {
        Write-Check "dist/ up to date" "PASS"
    }
}

if ($needBuild -and $npmOk) {
    Write-Host ""
    Write-Host "    Running npm run build..." -ForegroundColor Cyan
    Push-Location $WebRoot
    $ErrorActionPreference = "Continue"
    try {
        $buildOutput = & $Npm run build 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Check "Frontend build done" "PASS"
        } else {
            $errLines = ($buildOutput | Select-Object -Last 15) -join "`n"
            Write-Check "Frontend build failed" "FAIL" "exit code: $LASTEXITCODE"
            Write-Host ""
            Write-Host $errLines -ForegroundColor DarkGray
            Write-Host ""
            Write-Host "    Use -SkipBuild to skip and use old dist/" -ForegroundColor Yellow

            if (Test-Path $distIndex) {
                Write-Check "Falling back to old dist/" "WARN"
            } else {
                Write-Host "    No dist/ available, cannot start" -ForegroundColor Red
                exit 1
            }
        }
    } finally {
        $ErrorActionPreference = "Stop"
        Pop-Location
    }
} elseif ($needBuild -and -not $npmOk) {
    if (Test-Path $distIndex) {
        Write-Check "npm unavailable, using existing dist/" "WARN"
    } else {
        Write-Check "npm unavailable and no dist/" "FAIL"
        exit 1
    }
}

Write-Host ""

# ============================================================
#  Step 7: Start server
# ============================================================
Write-Host "  [7/7] Server" -ForegroundColor White
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray

if (-not (Test-Path $WebServer)) {
    Write-Check "web_server.py not found" "FAIL"
    exit 1
}

Write-Check "web_server.py" "PASS"

# Summary
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Cyan
$summary = "  Result: $passCount passed"
if ($warnCount -gt 0) { $summary += ", $warnCount warnings" }
if ($failCount -gt 0) { $summary += ", $failCount failed" }
$color = if ($failCount -gt 0) { "Red" } elseif ($warnCount -gt 0) { "Yellow" } else { "Green" }
Write-Host $summary -ForegroundColor $color
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

$url = "http://${BindHost}:${Port}"
Write-Host "  URL:    $url" -ForegroundColor Green
Write-Host "  Python: $Python" -ForegroundColor DarkGray
if ($condaActivated) {
    Write-Host "  Conda:  AiCad (activated)" -ForegroundColor DarkGray
}
Write-Host "  Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host ""

# Auto open browser
if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        Start-Sleep -Seconds 2
        Start-Process $using:url
    } | Out-Null
}

# Load .env file (GLM_API_KEY etc.)
$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
            $parts = $line -split '=', 2
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
        }
    }
    Write-Host "  .env loaded" -ForegroundColor DarkGray
}

# Launch
& $Python $WebServer --host $BindHost --port $Port
