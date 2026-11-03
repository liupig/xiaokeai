# MiniCPM-V 4.7 1B. One window.
# A new start kills whatever is still on port 8766.
# Closing this window kills the server started here.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$app = Join-Path $PSScriptRoot "app.py"
if (-not (Test-Path -LiteralPath $py)) {
  throw "No .venv yet. Run .\setup.ps1 first."
}

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

function Stop-AppPy {
  $root = $PSScriptRoot
  Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | ForEach-Object {
    $cmd = [string]$_.CommandLine
    if ($cmd -and ($cmd.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0) -and ($cmd -like "*app.py*")) {
      Stop-PidTree ([int]$_.ProcessId)
    }
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

Write-Host "Stopping the previous watcher..."
Stop-Port 8766
Stop-AppPy
Start-Sleep -Milliseconds 400

if (-not [ChildJob]::Start()) { throw "Could not arm the close-to-stop job." }
$proc = Start-Process -FilePath $py -ArgumentList @($app) -WorkingDirectory $PSScriptRoot -PassThru -NoNewWindow
$joined = [ChildJob]::Add($proc.Id)
Write-Host "http://127.0.0.1:8766"
if ($joined) {
  Write-Host "Close this window to stop the watcher."
} else {
  Write-Host "Close this window, or press Ctrl+C, to stop the watcher."
}

try {
  Wait-Process -Id $proc.Id
} finally {
  Stop-PidTree $proc.Id
  Stop-Port 8766
}
