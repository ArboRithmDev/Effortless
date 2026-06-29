#Requires -Version 5.1
<#
.SYNOPSIS
    Installation and deployment script for Effortless (Windows / PowerShell).

.DESCRIPTION
    Windows counterpart of setup.sh. Installs uv, creates the Python venv for the
    MCP server, builds the web dashboard, auto-deploys to detected MCP clients and
    installs the anti-drift Git pre-commit hook.

.NOTES
    Run from the repo root. If the script is blocked by the execution policy:
        powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

$ErrorActionPreference = 'Stop'

# --- Helpers ---------------------------------------------------------------
function Write-Step { param([string]$Msg) Write-Host $Msg -ForegroundColor Blue }
function Write-Ok   { param([string]$Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }

# Resolve paths relative to this script, not the caller's CWD.
$ProjectRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path
$McpServerDir = Join-Path $ProjectRoot 'src\mcp-server'
$VenvDir      = Join-Path $McpServerDir '.venv'
$VenvPython   = Join-Path $VenvDir 'Scripts\python.exe'

Write-Host "============================================================" -ForegroundColor Blue
Write-Host " EFFORTLESS - INSTALL & CONFIGURATION SCRIPT" -ForegroundColor Blue
Write-Host "============================================================" -ForegroundColor Blue

# --- 1. uv ------------------------------------------------------------------
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warn "Package manager 'uv' not detected. Installing via the official script..."
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    # uv installs into %USERPROFILE%\.local\bin — add it to the current session PATH.
    $UvBin = Join-Path $env:USERPROFILE '.local\bin'
    if (Test-Path $UvBin) { $env:Path = "$UvBin;$env:Path" }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "'uv' still not on PATH after install. Open a new terminal and re-run .\setup.ps1"
    }
} else {
    Write-Ok "'uv' is installed."
}

# --- 2. Python venv + dependencies -----------------------------------------
Write-Host ""
Write-Step "[1/4] Configuring the Python environment..."
Push-Location $McpServerDir
try {
    if (-not (Test-Path '.venv')) {
        Write-Host "Creating the virtual environment (.venv)..."
        uv venv
    } else {
        Write-Host "Virtual environment already exists."
    }
    # uv auto-discovers the .venv in the working directory — no activation needed.
    Write-Host "Installing project dependencies (editable + pytest)..."
    uv pip install -e . pytest
} finally {
    Pop-Location
}

# --- 3. Web dashboard (optional, needs npm) --------------------------------
Write-Host ""
Write-Step "[2/4] Building the web dashboard..."
$WebUiDir = Join-Path $ProjectRoot 'src\web-ui'
if (Get-Command npm -ErrorAction SilentlyContinue) {
    npm --prefix $WebUiDir install --no-audit --no-fund
    npm --prefix $WebUiDir run build
    Write-Ok "Web dashboard built (src/web-ui/dist)."
} else {
    Write-Warn "'npm' not found - dashboard not built. Install Node.js then run: cd src\web-ui; npm install; npm run build"
}

# --- 4. Multi-CLI / multi-App deployment -----------------------------------
Write-Host ""
Write-Step "[3/4] Auto-deploying to detected MCP clients..."
& $VenvPython -c "from effortless_mcp.server import effortless_deploy; print(effortless_deploy())"

# --- 5. Anti-drift Git pre-commit hook -------------------------------------
Write-Host ""
Write-Step "[4/4] Installing the anti-drift Git pre-commit hook..."
& $VenvPython -c "from effortless_mcp.server import effortless_drift_hook_install; print(effortless_drift_hook_install())"

# --- Success ----------------------------------------------------------------
Write-Host ""
Write-Ok "Install, deployment and hardening completed successfully!"
Write-Host "============================================================" -ForegroundColor Blue
Write-Host "AVAILABLE COMMANDS:" -ForegroundColor Yellow
Write-Host "* Run the MCP server locally:"
Write-Host "  cd src\mcp-server; .\.venv\Scripts\Activate.ps1; effortless-mcp" -ForegroundColor Green
Write-Host "* Run the interactive CLI test client:"
Write-Host "  & '$VenvPython' src\cli\main.py" -ForegroundColor Green
Write-Host "* Run the unit tests:"
Write-Host "  cd src\mcp-server; .\.venv\Scripts\Activate.ps1; pytest" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Blue
