#Requires -Version 5.1
<#
.SYNOPSIS
    One-shot development setup for Windows.

.DESCRIPTION
    Creates the virtual environment, installs the backend and frontend
    dependencies, downloads the Chromium build Playwright drives, and writes a
    .env with freshly generated keys. Safe to re-run: nothing that already
    exists is recreated, and an existing .env is never overwritten.

.EXAMPLE
    .\scripts\setup.ps1
#>

$ErrorActionPreference = 'Stop'

$RepoRoot    = Split-Path -Parent $PSScriptRoot
$VenvDir     = Join-Path $RepoRoot '.venv'
$EnvFile     = Join-Path $RepoRoot '.env'
$EnvTemplate = Join-Path $RepoRoot '.env.example'
$MinMajor    = 3
$MinMinor    = 11

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Info { param([string]$Message) Write-Host "    $Message" }

function Stop-WithError {
    param([string]$Message)
    Write-Host "`nERROR: $Message" -ForegroundColor Red
    exit 1
}

function Invoke-Native {
    <#
        Runs an external program and returns its exit code. Windows PowerShell 5.1
        turns a native command's stderr output into error records, which would
        abort the script on any tool that merely prints a warning (pip and npm
        both do), so the preference is relaxed for the duration of the call.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [switch]$Quiet
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($Quiet) {
            & $FilePath @Arguments | Out-Null
        } else {
            & $FilePath @Arguments
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

Set-Location $RepoRoot

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
Write-Step 'Checking Python'
$pythonExe = $null
$pythonArgs = @()
$probe = "import sys; sys.exit(0 if sys.version_info >= ($MinMajor, $MinMinor) else 1)"

foreach ($candidate in @('python', 'python3', 'py')) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($null -eq $command) { continue }

    if ($candidate -eq 'py') { $tryArgs = @("-$MinMajor") } else { $tryArgs = @() }
    $code = Invoke-Native -FilePath $command.Source -Arguments ($tryArgs + @('-c', $probe)) -Quiet
    if ($code -eq 0) {
        $pythonExe = $command.Source
        $pythonArgs = $tryArgs
        break
    }
}

if ($null -eq $pythonExe) {
    Stop-WithError @"
Python $MinMajor.$MinMinor or newer is required but was not found.
       Install it from https://www.python.org/downloads/ (tick
       "Add python.exe to PATH") and run this script again.
"@
}

$versionLine = (Invoke-Native -FilePath $pythonExe -Arguments ($pythonArgs + @('--version'))) -join ''
Write-Info "using $versionLine at $pythonExe"

# ---------------------------------------------------------------------------
# Virtual environment and backend dependencies
# ---------------------------------------------------------------------------
Write-Step 'Creating the virtual environment'
if (Test-Path $VenvDir) {
    Write-Info '.venv already exists, reusing it'
} else {
    if ((Invoke-Native -FilePath $pythonExe -Arguments ($pythonArgs + @('-m', 'venv', $VenvDir))) -ne 0) {
        Stop-WithError 'Could not create the virtual environment.'
    }
    Write-Info 'created .venv'
}

$VenvPy = Join-Path $VenvDir 'Scripts\python.exe'
if (-not (Test-Path $VenvPy)) {
    Stop-WithError @"
The virtual environment looks broken: $VenvPy is missing.
       Delete .venv and run this script again.
"@
}

Write-Step 'Installing the backend (this takes a minute)'
Invoke-Native -FilePath $VenvPy -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip') -Quiet | Out-Null
if ((Invoke-Native -FilePath $VenvPy -Arguments @('-m', 'pip', 'install', '-e', '.[dev]')) -ne 0) {
    Stop-WithError 'Backend installation failed.'
}

Write-Step 'Installing the Chromium build Playwright drives'
if ((Invoke-Native -FilePath $VenvPy -Arguments @('-m', 'playwright', 'install', 'chromium')) -ne 0) {
    Stop-WithError 'Could not download Chromium.'
}

# ---------------------------------------------------------------------------
# Frontend dependencies
# ---------------------------------------------------------------------------
Write-Step 'Installing the frontend'
$npm = Get-Command npm -ErrorAction SilentlyContinue
$frontendDir = Join-Path $RepoRoot 'frontend'
$frontendPackage = Join-Path $frontendDir 'package.json'
if ($null -eq $npm) {
    Write-Info 'npm was not found - skipping. Install Node.js 20+ from https://nodejs.org'
    Write-Info 'and then run: cd frontend; npm install'
} elseif (-not (Test-Path $frontendPackage)) {
    Write-Info 'frontend\package.json does not exist yet - skipping'
} else {
    Push-Location $frontendDir
    try {
        if ((Invoke-Native -FilePath $npm.Source -Arguments @('install', '--no-audit', '--no-fund')) -ne 0) {
            Stop-WithError 'npm install failed.'
        }
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
Write-Step 'Preparing .env'
if (Test-Path $EnvFile) {
    Write-Info '.env already exists, leaving it untouched'
} else {
    if (-not (Test-Path $EnvTemplate)) {
        Stop-WithError "$EnvTemplate is missing; cannot create .env."
    }

    function New-UrlSafeKey {
        $bytes = New-Object 'System.Byte[]' 36
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        # URL-safe base64, matching secrets.token_urlsafe on the Python side.
        [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_').TrimEnd('=')
    }

    $secretKey = New-UrlSafeKey
    $encryptionKey = New-UrlSafeKey

    $secretDone = $false
    $encryptionDone = $false
    $output = foreach ($line in (Get-Content -Path $EnvTemplate -Encoding UTF8)) {
        if (-not $secretDone -and $line -match '^SECRET_KEY=') {
            $secretDone = $true
            "SECRET_KEY=$secretKey"
        } elseif (-not $encryptionDone -and $line -match '^ENCRYPTION_KEY=') {
            $encryptionDone = $true
            "ENCRYPTION_KEY=$encryptionKey"
        } else {
            $line
        }
    }

    $output | Out-File -FilePath $EnvFile -Encoding utf8
    Write-Info 'created .env with a fresh SECRET_KEY and ENCRYPTION_KEY'
}

# ---------------------------------------------------------------------------
# What to do next
# ---------------------------------------------------------------------------
Write-Host @'

Setup finished. Three things left:

  1. Add your Anthropic API key to .env
         ANTHROPIC_API_KEY=sk-ant-...
     Get one at https://console.anthropic.com/

  2. Create the database and an account
         cd backend; ..\.venv\Scripts\alembic upgrade head; cd ..
         .venv\Scripts\python scripts\create_user.py

  3. Start the app (two terminals)
         .venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --port 8000
         cd frontend; npm run dev
     Backend  http://localhost:8000   (API docs at /docs)
     Frontend http://localhost:5173

Then, inside the app, open the browser session and sign in to LinkedIn by hand.
Only the session cookies are stored, encrypted; your LinkedIn password never is.

Nothing is ever submitted without you confirming it explicitly.
'@
