# Start isolated MiniCPM-o demo
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
  throw "No .venv yet. Run .\setup.ps1 first."
}
Write-Host "http://127.0.0.1:8765"
& $py (Join-Path $PSScriptRoot "app.py")
