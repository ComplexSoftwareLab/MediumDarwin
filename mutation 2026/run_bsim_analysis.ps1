# Regenerate BSim clustering results for the Mutation 2026 paper.
# Usage (from this folder):
#   .\run_bsim_analysis.ps1
#   .\run_bsim_analysis.ps1 -Projects triangle-example,jra
#   .\run_bsim_analysis.ps1 -ClearCache -Verbose

param(
    [string]$Projects = "",
    [switch]$NoCache,
    [switch]$ClearCache,
    [switch]$SkipDownload,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$LogDir = Join-Path $Root "logs"
$ResultsDir = Join-Path $Root "results"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$LogFile = Join-Path $LogDir "bsim_analysis.log"

# UTF-8 console + Python I/O (Windows)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [Console]::OutputEncoding
} catch {
    # Older hosts: Python configure_stdio() still applies.
}

$Python = $null
if (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
elseif (Get-Command python3 -ErrorAction SilentlyContinue) { $Python = "python3" }
else { throw "Python not found on PATH." }

& $Python -c "import community, scipy, networkx, matplotlib, numpy, tqdm, gdown" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing Python dependencies ..."
    & $Python -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install requirements.txt"
    }
}

if (-not $SkipDownload) {
    $downloadArgs = @((Join-Path $Root "download_databases.py"))
    if ($Projects) {
        $downloadArgs += "--projects"
        $downloadArgs += ($Projects -split "," | ForEach-Object { $_.Trim() })
    }
    & $Python @downloadArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Database download failed (exit $LASTEXITCODE)"
    }
}

$runnerArgs = @(
    (Join-Path $Root "run_all_projects.py"),
    "--output-dir", $ResultsDir,
    "--log-file", $LogFile
)
if ($Projects) {
    $runnerArgs += "--projects"
    $runnerArgs += ($Projects -split "," | ForEach-Object { $_.Trim() })
}
if ($NoCache) { $runnerArgs += "--no-cache" }
if ($ClearCache) { $runnerArgs += "--clear-cache" }
if ($Verbose) { $runnerArgs += "--verbose" }

# Python writes a clean UTF-8 log via --log-file; console keeps live tqdm bars.
& $Python @runnerArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Analysis pipeline failed (exit $LASTEXITCODE)"
}

Write-Host ""
Write-Host "Done. Results in $ResultsDir"
Write-Host "Log file: $LogFile"
