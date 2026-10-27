# xiaoke.ai desktop: backend 8600 + frontend 5175 + Electron.
# A new start kills the previous backend, frontend, and this desktop shell.
# Closing this window, or closing the desktop window, stops all three.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$root = $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
$front = Join-Path $root "frontend"
$desk = Join-Path $root "desktop"
$logDir = Join-Path $root "backend\data\launch-logs"
if (-not (Test-Path -LiteralPath $py)) { throw "No backend\.venv. See companion\README.md." }
if (-not (Test-Path -LiteralPath (Join-Path $front "node_modules"))) { throw "No frontend\node_modules. Run npm install in frontend." }
if (-not (Test-Path -LiteralPath (Join-Path $desk "node_modules"))) { throw "No desktop\node_modules. Run npm install in desktop." }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Stop-PidTree([int]$ProcId) {
  if ($ProcId -le 0 -or $ProcId -eq $PID) { return }
  & taskkill.exe /PID $ProcId /T /F 2>$null | Out-Null
}

function Stop-Port([int]$Port) {
  $ids = New-Object System.Collections.Generic.List[int]
  $raw = & netstat.exe -ano -p tcp
  foreach ($line in $raw) {
    if ($line -notmatch "LISTENING") { continue }
    $parts = ($line -split "\s+") | Where-Object { $_ -ne "" }
    if ($parts.Count -lt 5) { continue }
    $local = [string]$parts[1]
    $sep = $local.LastIndexOf(":")
    if ($sep -lt 0) { continue }
    if ($local.Substring($sep + 1) -ne "$Port") { continue }
    $listen = 0
    [void][int]::TryParse([string]$parts[$parts.Count - 1], [ref]$listen)
    if ($listen -gt 0 -and -not $ids.Contains($listen)) { $ids.Add($listen) }
  }
  foreach ($listen in $ids) { Stop-PidTree $listen }
}

function Stop-Matching([string]$fragment) {
  Get-CimInstance Win32_Process | ForEach-Object {
    $cmd = [string]$_.CommandLine
    if (-not $cmd) { return }
    if ($cmd.IndexOf($fragment, [StringComparison]::OrdinalIgnoreCase) -lt 0) { return }
    if ([int]$_.ProcessId -eq $PID) { return }
    Stop-PidTree ([int]$_.ProcessId)
  }
}

if (-not ("ChildJob" -as [type])) {
  Add-Type -TypeDefinition @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
public static class ChildJob {
  const int JobObjectExtendedLimitInformation = 9;
  const uint KillOnJobClose = 0x2000;
  [StructLayout(LayoutKind.Sequential)]
  struct Basic {
    public long PerProcessUserTimeLimit;
    public long PerJobUserTimeLimit;
    public uint LimitFlags;
    public UIntPtr MinimumWorkingSetSize;
    public UIntPtr MaximumWorkingSetSize;
    public uint ActiveProcessLimit;
    public UIntPtr Affinity;
    public uint PriorityClass;
    public uint SchedulingClass;
  }
  [StructLayout(LayoutKind.Sequential)]
  struct Counters {
    public ulong ReadOperationCount;
    public ulong WriteOperationCount;
    public ulong OtherOperationCount;
    public ulong ReadTransferCount;
    public ulong WriteTransferCount;
    public ulong OtherTransferCount;
  }
  [StructLayout(LayoutKind.Sequential)]
  struct Extended {
    public Basic BasicLimitInformation;
    public Counters IoInfo;
    public UIntPtr ProcessMemoryLimit;
    public UIntPtr JobMemoryLimit;
    public UIntPtr PeakProcessMemoryUsed;
    public UIntPtr PeakJobMemoryUsed;
  }
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
  static extern IntPtr CreateJobObject(IntPtr a, string name);
  [DllImport("kernel32.dll")]
  static extern bool SetInformationJobObject(IntPtr hJob, int cls, ref Extended info, uint len);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
  delegate bool CtrlHandler(int ctrl);
  [DllImport("kernel32.dll")]
  static extern bool SetConsoleCtrlHandler(CtrlHandler handler, bool add);
  static IntPtr handle;
  static CtrlHandler keep;
  static readonly System.Collections.Generic.List<int> pids = new System.Collections.Generic.List<int>();
  static void KillPort(int port) {
    try {
      var info = new ProcessStartInfo();
      info.FileName = "netstat.exe";
      info.Arguments = "-ano -p tcp";
      info.CreateNoWindow = true;
      info.UseShellExecute = false;
      info.RedirectStandardOutput = true;
      using (var probe = Process.Start(info)) {
        if (probe == null) return;
        var text = probe.StandardOutput.ReadToEnd();
        probe.WaitForExit(4000);
        var seen = new System.Collections.Generic.HashSet<int>();
        foreach (var raw in text.Split('\n')) {
          if (raw.IndexOf("LISTENING", StringComparison.OrdinalIgnoreCase) < 0) continue;
          var parts = raw.Split(new char[] { ' ', '\t', '\r' }, StringSplitOptions.RemoveEmptyEntries);
          if (parts.Length < 5) continue;
          if (!parts[1].EndsWith(":" + port)) continue;
          int pid;
          if (!int.TryParse(parts[parts.Length - 1], out pid) || pid <= 0 || seen.Contains(pid)) continue;
          seen.Add(pid);
          try {
            var kill = new ProcessStartInfo();
            kill.FileName = "taskkill.exe";
            kill.Arguments = "/PID " + pid + " /T /F";
            kill.CreateNoWindow = true;
            kill.UseShellExecute = false;
            using (var killer = Process.Start(kill)) {
              if (killer != null) killer.WaitForExit(4000);
            }
          } catch { }
        }
      }
    } catch { }
  }
  static void KillAll() {
    foreach (var pid in pids.ToArray()) {
      try {
        var info = new ProcessStartInfo();
        info.FileName = "taskkill.exe";
        info.Arguments = "/PID " + pid + " /T /F";
        info.CreateNoWindow = true;
        info.UseShellExecute = false;
        using (var killer = Process.Start(info)) {
          if (killer != null) killer.WaitForExit(4000);
        }
      } catch { }
    }
    KillPort(8766);
  }
  public static bool Start() {
    if (handle != IntPtr.Zero) return true;
    handle = CreateJobObject(IntPtr.Zero, null);
    if (handle == IntPtr.Zero) return false;
    var info = new Extended();
    info.BasicLimitInformation.LimitFlags = KillOnJobClose;
    var armed = SetInformationJobObject(handle, JobObjectExtendedLimitInformation, ref info, (uint)Marshal.SizeOf(typeof(Extended)));
    keep = ctrl => {
      if (ctrl == 0) return false;
      KillAll();
      return false;
    };
    SetConsoleCtrlHandler(keep, true);
    return armed;
  }
  public static bool Add(int pid) {
    if (!pids.Contains(pid)) pids.Add(pid);
    try {
      using (var proc = Process.GetProcessById(pid)) {
        return AssignProcessToJobObject(handle, proc.Handle);
      }
    } catch {
      return false;
    }
  }
}
"@
}

function Wait-Port([int]$Port, [int]$Seconds) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    $raw = & netstat.exe -ano -p tcp
    foreach ($line in $raw) {
      if ($line -notmatch "LISTENING") { continue }
      $parts = ($line -split "\s+") | Where-Object { $_ -ne "" }
      if ($parts.Count -lt 5) { continue }
      $local = [string]$parts[1]
      $sep = $local.LastIndexOf(":")
      if ($sep -ge 0 -and $local.Substring($sep + 1) -eq "$Port") { return $true }
    }
    Start-Sleep -Milliseconds 400
  } while ((Get-Date) -lt $deadline)
  return $false
}

function Start-Logged([string]$name, [string]$workdir, [string]$command) {
  $out = Join-Path $logDir "$name.out.log"
  $err = Join-Path $logDir "$name.err.log"
  if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Force -ErrorAction SilentlyContinue }
  if (Test-Path -LiteralPath $err) { Remove-Item -LiteralPath $err -Force -ErrorAction SilentlyContinue }
  $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/s", "/c", $command) -WorkingDirectory $workdir -PassThru -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
  [void][ChildJob]::Add($proc.Id)
  return $proc
}

$kids = @()
function Stop-Kids {
  foreach ($proc in $kids) {
    if ($proc -and -not $proc.HasExited) { Stop-PidTree $proc.Id }
  }
  Stop-Port 8600
  Stop-Port 5175
  Stop-Port 8766
}

Write-Host "Stopping the previous desktop, backend, and frontend..."
Stop-Matching (Join-Path $desk "node_modules")
Stop-Matching (Join-Path $front "node_modules\vite")
Stop-Port 5175
Stop-Port 8600
Stop-Port 8766
Stop-Matching (Join-Path $root "backend")
Start-Sleep -Milliseconds 600

if (-not [ChildJob]::Start()) { throw "Could not arm the close-to-stop job." }
$env:NO_PROXY = "*"
$env:PYTHONUNBUFFERED = "1"
$env:COMPANION_HOME = "http://127.0.0.1:5175/"

$backend = Start-Logged "backend" (Join-Path $root "backend") "`"$py`" -m uvicorn app.main:app --host 127.0.0.1 --port 8600"
$kids += $backend
if (-not (Wait-Port 8600 40)) {
  Stop-Kids
  throw "Backend did not listen on 8600. See $logDir\backend.err.log"
}
Write-Host "Backend  http://127.0.0.1:8600"

$frontend = Start-Logged "frontend" $front "npm run dev"
$kids += $frontend
if (-not (Wait-Port 5175 40)) {
  Stop-Kids
  throw "Frontend did not listen on 5175. See $logDir\frontend.err.log"
}
Write-Host "Frontend http://127.0.0.1:5175"

$desktop = Start-Logged "desktop" $desk "npm run dev"
$kids += $desktop
Write-Host "Desktop window is opening."
Write-Host "Close this window, or close the desktop window, to stop backend, frontend, and vision."

try {
  Wait-Process -Id $desktop.Id
} finally {
  Stop-Kids
}
