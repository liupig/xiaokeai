param([int]$Port = 8610, [switch]$Rebuild, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$labRoot = $PSScriptRoot
$labPython = Join-Path $labRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $labPython)) { throw '请先安装项目的 backend/.venv 依赖。' }
$labPage = Join-Path $labRoot 'frontend\dist\live-lab.html'
if ($Rebuild -or -not (Test-Path -LiteralPath $labPage)) {
    Push-Location (Join-Path $labRoot 'frontend')
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
    } finally { Pop-Location }
}
$labUrl = "http://127.0.0.1:$Port/live-lab.html"
Write-Host "直播彩排：$labUrl"
Write-Host 'Ctrl+C 停止。虚构观众不会连接真实平台，脚本模式不需要模型密钥。'
$labLogDir = Join-Path $labRoot 'backend\data'
[IO.Directory]::CreateDirectory($labLogDir) | Out-Null
$labLogId = [Guid]::NewGuid().ToString('N')
$labOut = Join-Path $labLogDir "live-lab-$labLogId.out.log"
$labErr = Join-Path $labLogDir "live-lab-$labLogId.err.log"
$labProcess = Start-Process -FilePath $labPython -ArgumentList @('-m', 'uvicorn', 'app.modules.live.lab_app:app', '--host', '127.0.0.1', '--port', "$Port", '--no-access-log') -WorkingDirectory (Join-Path $labRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput $labOut -RedirectStandardError $labErr
try {
    $labReady = $false
    for ($labAttempt = 0; $labAttempt -lt 100; $labAttempt++) {
        if ($labProcess.HasExited) { throw "彩排启动失败，日志：$labErr" }
        try {
            $labHealth = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/live-lab/state" -UseBasicParsing -TimeoutSec 1
            if ($labHealth.StatusCode -eq 200) { $labReady = $true; break }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    if (-not $labReady) { throw "彩排服务没有就绪，日志：$labErr" }
    if (-not $NoBrowser) { Start-Process $labUrl }
    while (-not $labProcess.HasExited) { Start-Sleep -Seconds 1 }
} finally {
    if (-not $labProcess.HasExited) { Stop-Process -Id $labProcess.Id }
}
