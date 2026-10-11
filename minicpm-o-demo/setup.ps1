# MiniCPM-o 4.5 isolated demo setup (ASCII only for Windows PowerShell 5)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Py310 {
  $cands = @(
    "D:\BingSoft\Anaconda\envs\base12\python.exe",
    "D:\BingSoft\Anaconda\envs\python-312-vllm\python.exe",
    "C:\Python311\python.exe",
    "C:\Python313\python.exe"
  )
  foreach ($p in $cands) {
    if (Test-Path -LiteralPath $p) { return $p }
  }
  return $null
}

$py = Find-Py310
if (-not $py) { throw "Need Python 3.10+. base12 / python-312-vllm conda envs not found." }

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
  Write-Host "Creating .venv with $py"
  & $py -m venv .venv
}

Write-Host "Installing torch 2.6 CUDA into this venv only..."
& $venvPy -m pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $venvPy -m pip install "torch==2.6.0" "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cu124
if ($LASTEXITCODE -ne 0) { throw "torch CUDA install failed" }
Write-Host "Installing MiniCPM-o deps (transformers==4.51.0)..."
& $venvPy -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw "requirements install failed" }
# Re-pin CUDA torch in case pip pulled a CPU wheel via accelerate
& $venvPy -m pip install "torch==2.6.0" "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cu124
if ($LASTEXITCODE -ne 0) { throw "torch CUDA re-pin failed" }

$what = "gguf"
if ($args.Count -gt 0) { $what = $args[0] }
Write-Host "Downloading weights: $what"
& $venvPy (Join-Path $PSScriptRoot "download.py") $what

Write-Host ""
Write-Host "Next: .\start.ps1"
Write-Host "Open http://127.0.0.1:8765"
