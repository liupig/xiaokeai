# xiaoke.ai Code 伴侣：Cursor hook → 本机后端。只向 stdout 打 JSON，避免挡对话。
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
$InformationPreference = 'SilentlyContinue'
try {
  $raw = [Console]::In.ReadToEnd()
} catch {
  $raw = ''
}
if (-not $raw) {
  [Console]::Out.Write('{}')
  exit 0
}

$ports = @(8600, 5201)
$hint = Join-Path $env:USERPROFILE '.cursor\xiaoke-codewatch.json'
if (Test-Path $hint) {
  try {
    $cfg = Get-Content -Raw -Path $hint | ConvertFrom-Json
    if ($cfg.ports) { $ports = @($cfg.ports) + $ports }
  } catch {}
}

foreach ($p in $ports) {
  try {
    $null = Invoke-WebRequest -UseBasicParsing -Method POST `
      -Uri ("http://127.0.0.1:{0}/api/modules/codewatch/hook" -f $p) `
      -ContentType 'application/json; charset=utf-8' `
      -Body ([System.Text.Encoding]::UTF8.GetBytes($raw)) `
      -TimeoutSec 1
    break
  } catch {}
}
[Console]::Out.Write('{}')
exit 0
