# Download Mutation 2026 SQLite databases from Google Drive.
# Usage:
#   .\download_databases.ps1
#   .\download_databases.ps1 -Projects triangle-example,jra
#   .\download_databases.ps1 -Force

param(
    [string]$Projects = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Python = $null
if (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
elseif (Get-Command python3 -ErrorAction SilentlyContinue) { $Python = "python3" }
else { throw "Python not found on PATH." }

$downloadArgs = @((Join-Path $Root "download_databases.py"))
if ($Projects) {
    $downloadArgs += "--projects"
    $downloadArgs += ($Projects -split "," | ForEach-Object { $_.Trim() })
}
if ($Force) { $downloadArgs += "--force" }

& $Python @downloadArgs
if ($LASTEXITCODE -ne 0) {
    throw "Database download failed (exit $LASTEXITCODE)"
}
