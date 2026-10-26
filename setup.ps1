# One install step. Houdini must already be installed.
# Restart Houdini after this. Opening the shelf starts Temporal.

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path

$hython = Get-ChildItem "C:\Program Files\Side Effects Software" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "bin\hython.exe" } |
    Where-Object { Test-Path $_ } |
    Select-Object -Last 1
if (-not $hython) {
    throw "Houdini was not found. Install Houdini, then run this script again."
}

& $hython -m pip install --user -e $Repo
if ($LASTEXITCODE -ne 0) { throw "The shelf package did not install into Houdini's Python." }

$pref = (& $hython -c "import os; print(os.environ.get('HOUDINI_USER_PREF_DIR',''))").Trim()
if (-not $pref) {
    $pref = Join-Path $env:USERPROFILE "Documents\houdini22.0"
}
$toolbar = Join-Path $pref "toolbar"
New-Item -ItemType Directory -Force -Path $toolbar | Out-Null
Copy-Item (Join-Path $Repo "shelf\houdini_wizard.shelf") (Join-Path $toolbar "houdini_wizard.shelf") -Force

& $hython -c "from houdini_wizard.service import ensure_cli; print(ensure_cli())"
if ($LASTEXITCODE -ne 0) { throw "Temporal could not be prepared." }

Write-Host ""
Write-Host "Installed. Restart Houdini. The shelf tab is Houdini Wizard, and the tool is Section card."
Write-Host "Opening the tool starts recovery in the background. Session log and Developer monitor are buttons on the panel."
Write-Host "Quotes work without a model. For heading picks, install Ollama, then run: ollama pull gemma3:4b"
Write-Host "The steps are in README.md under Ollama and Gemma."
Write-Host "Read more about the agent session behind this code is linked on the Session log page: https://entire.com/gh/AbisoyeOnanuga/houdini-wizard/session/e96d75ea-ea02-4990-b94a-81678a4c1465"
