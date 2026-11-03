# MiniCPM-V 4.7 1B screen watcher. Own venv. ASCII only for Windows PowerShell 5.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Py {
  $cands = @(
    "D:\BingSoft\Anaconda\envs\base12\python.exe",
    "D:\BingSoft\Anaconda\envs\python-312-vllm\python.exe",
    "C:\Python311\python.exe",
    "C:\Python313\python.exe"
  )
  foreach ($p in $cands) {
    if (Test-Path -LiteralPath $p) { return $p }
  }
  $cmd = Get-Command py -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

$py = Find-Py
if (-not $py) { throw "Need Python 3.10+." }

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
  Write-Host "Creating v47 .venv with $py"
  & $py -m venv .venv
}

Write-Host "Installing CUDA torch into v47 .venv only..."
& $venvPy -m pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

# This machine already runs torch 2.8+cu128. Pip from download.pytorch.org
# dropped the 2.5GB wheel mid-transfer, so download with curl resume first.
$wheelDir = Join-Path $PSScriptRoot "wheels"
New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null
$torchName = "torch-2.8.0+cu128-cp312-cp312-win_amd64.whl"
$visionName = "torchvision-0.23.0+cu128-cp312-cp312-win_amd64.whl"
$pairs = @(
  @{ Name = $torchName; Url = "https://download.pytorch.org/whl/cu128/$($torchName -replace '\+','%2B')" },
  @{ Name = $visionName; Url = "https://download.pytorch.org/whl/cu128/$($visionName -replace '\+','%2B')" }
)
foreach ($item in $pairs) {
  $dest = Join-Path $wheelDir $item.Name
  $remote = 0L
  $hdr = & curl.exe -sI -L --max-time 20 $item.Url
  foreach ($line in $hdr) {
    if ($line -match "(?i)^content-length:\s*(\d+)") { $remote = [int64]$Matches[1] }
  }
  $local = 0L
  if (Test-Path -LiteralPath $dest) { $local = (Get-Item -LiteralPath $dest).Length }
  if ($remote -gt 0 -and $local -eq $remote) {
    Write-Host "Already have $($item.Name)"
    continue
  }
  Write-Host "Downloading $($item.Name)"
  # Drop the connection if it stalls, then resume the same file.
  & curl.exe -L --retry 20 --retry-delay 2 --retry-all-errors -C - --speed-time 20 --speed-limit 200000 -o $dest $item.Url
  if ($LASTEXITCODE -ne 0) { throw "download failed: $($item.Name)" }
}
& $venvPy -m pip install (Join-Path $wheelDir $torchName) (Join-Path $wheelDir $visionName) -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw "torch CUDA install failed" }
Write-Host "Installing MiniCPM-V 4.7 deps (transformers>=5.18)..."
& $venvPy -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw "requirements install failed" }
# Keep the CUDA wheel if the mirror replaced torch with a CPU build.
& $venvPy -m pip install (Join-Path $wheelDir $torchName) (Join-Path $wheelDir $visionName) -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw "torch CUDA re-pin failed" }

Write-Host "Downloading MiniCPM-V-4.7-1B..."
& $venvPy (Join-Path $PSScriptRoot "download.py")
if ($LASTEXITCODE -ne 0) { throw "weight download failed" }

Write-Host ""
Write-Host "Next: .\start.ps1"
Write-Host "Open http://127.0.0.1:8766"
