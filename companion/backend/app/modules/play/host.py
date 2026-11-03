"""本机：注册表、文件、进程、启动。测试可以换一套假的。"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Proc:
    name: str
    exe: str = ""


@dataclass(frozen=True)
class Shortcut:
    name: str
    target: str
    args: str = ""
    workdir: str = ""


def clean_reg(raw: str) -> str:
    text = (raw or "").strip().strip('"').strip()
    if not text:
        return ""
    exe = text.lower().find(".exe")
    if exe >= 0:
        return text[: exe + 4].strip().strip('"')
    return text


class WindowsHost:
    def __init__(self) -> None:
        self._shortcut_cache: list[Shortcut] | None = None

    def reg_value(self, hive: str, path: str, name: str) -> str:
        if os.name != "nt":
            return ""
        import winreg

        root = winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        flags = (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
        for access in flags:
            try:
                with winreg.OpenKey(root, path, 0, access) as key:
                    value, kind = winreg.QueryValueEx(key, name)
            except OSError:
                continue
            if kind == winreg.REG_DWORD:
                continue
            text = clean_reg(str(value or ""))
            if text:
                return text
        return ""

    def reg_subkeys(self, hive: str, path: str) -> list[str]:
        if os.name != "nt":
            return []
        import winreg

        root = winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        found: list[str] = []
        seen: set[str] = set()
        flags = (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
        for access in flags:
            try:
                with winreg.OpenKey(root, path, 0, access) as key:
                    index = 0
                    while True:
                        try:
                            item = winreg.EnumKey(key, index)
                        except OSError:
                            break
                        index += 1
                        if item not in seen:
                            seen.add(item)
                            found.append(item)
            except OSError:
                continue
        return found

    def is_file(self, path: str) -> bool:
        return bool(path) and os.path.isfile(path)

    def is_dir(self, path: str) -> bool:
        return bool(path) and os.path.isdir(path)

    def read_text(self, path: str) -> str:
        try:
            with open(path, encoding="utf-8-sig") as handle:
                return handle.read()
        except OSError:
            return ""

    def read_bytes(self, path: str) -> bytes:
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            return b""

    def list_dir(self, path: str) -> list[str]:
        try:
            return os.listdir(path)
        except OSError:
            return []

    def env(self, key: str) -> str:
        return os.environ.get(key, "") or ""

    def drives(self) -> list[str]:
        if os.name != "nt":
            return []
        import ctypes
        import string

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        mask = int(kernel.GetLogicalDrives())
        found: list[str] = []
        for index, letter in enumerate(string.ascii_uppercase):
            if not mask & (1 << index):
                continue
            root = f"{letter}:\\"
            if int(kernel.GetDriveTypeW(root)) == 3:
                found.append(root)
        return found

    def spawn(self, argv: list[str]) -> None:
        if not argv or not argv[0]:
            raise OSError("empty command")
        if os.name == "nt":
            _shell_open(argv)
            return
        subprocess.Popen(
            argv,
            cwd=os.path.dirname(argv[0]) or None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )

    def processes(self) -> list[Proc]:
        if os.name != "nt":
            return []
        try:
            return _processes()
        except Exception:
            return []

    def shortcuts(self) -> list[Shortcut]:
        if self._shortcut_cache is None:
            self._shortcut_cache = _load_shortcuts()
        return list(self._shortcut_cache)

    def now(self) -> float:
        return time.time()

    def press_wegame_start(self) -> None:
        """WeGame 以高权限运行，普通进程点不到「启动」。比例点在窗口右下角那个按钮上。"""
        if os.name != "nt":
            return
        import tempfile

        path = os.path.join(tempfile.gettempdir(), "xiaoke-wegame-start.ps1")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_WEGAME_START_PS)
        _shell_open(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", path], verb="runas")


def _shell_open(argv: list[str], verb: str = "open") -> None:
    """跟双击快捷方式一样走 ShellExecute，需要提权的启动器才能拉起来。"""
    if os.name == "nt" and verb == "open":
        _detach_open(argv)
        return
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteW.argtypes = [
        wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int,
    ]
    shell32.ShellExecuteW.restype = wintypes.HINSTANCE
    params = subprocess.list2cmdline(argv[1:]) if len(argv) > 1 else None
    cwd = os.path.dirname(argv[0]) if argv and os.path.isfile(argv[0]) else None
    code = int(shell32.ShellExecuteW(None, verb, argv[0], params, cwd, 1))
    if code <= 32:
        raise OSError(code, f"无法打开 {argv[0]}")


def _detach_open(argv: list[str]) -> None:
    """游戏从本进程脱开。关窗口时的进程树清理和作业结束，不再把 WeGame、英雄联盟一起杀掉。"""
    if not argv or not argv[0]:
        raise OSError("empty command")
    exe = argv[0]
    cwd = os.path.dirname(exe) if os.path.isfile(exe) else None
    cmd = ["cmd.exe", "/d", "/c", "start", ""]
    if cwd:
        cmd.extend(["/D", cwd])
    cmd.extend(argv)
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    try:
        subprocess.Popen(cmd, creationflags=0x01000000, **kwargs)
    except OSError:
        subprocess.Popen(cmd, **kwargs)


# WeGame 的「启动」是页面里一颗橙色长按钮，辅助功能树里没有名字。
# 把窗口前面那一块屏幕抓下来，找最长的一段橙色，点它的中间。
_WEGAME_START_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text;
public class WgStart {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(int f, int dx, int dy, int data, int extra);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr h);
  [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr h, IntPtr hdc);
  [DllImport("gdi32.dll")] public static extern bool BitBlt(IntPtr dst, int x, int y, int w, int h, IntPtr src, int sx, int sy, int rop);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int ht, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
  static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  public static IntPtr found;
  static EnumProc keep;
  public static IntPtr Find() {
    found = IntPtr.Zero;
    keep = OnEnum;
    EnumWindows(keep, IntPtr.Zero);
    return found;
  }
  static bool OnEnum(IntPtr h, IntPtr l) {
    if (!IsWindowVisible(h)) return true;
    var sb = new StringBuilder(512);
    GetWindowText(h, sb, sb.Capacity);
    if (sb.ToString() == "WeGame") { found = h; return false; }
    return true;
  }
  public static bool Locate(IntPtr hwnd, out int absX, out int absY, out int run) {
    absX = absY = run = 0;
    RECT rect;
    if (!GetWindowRect(hwnd, out rect)) return false;
    int w = rect.Right - rect.Left;
    int h = rect.Bottom - rect.Top;
    if (w < 400 || h < 300) return false;
    using (var bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb)) {
      using (var g = Graphics.FromImage(bmp)) {
        IntPtr dst = g.GetHdc();
        IntPtr src = GetDC(IntPtr.Zero);
        BitBlt(dst, 0, 0, w, h, src, rect.Left, rect.Top, 0x00CC0020);
        ReleaseDC(IntPtr.Zero, src);
        g.ReleaseHdc(dst);
      }
      var bits = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
      int stride = bits.Stride;
      byte[] buf = new byte[stride * h];
      Marshal.Copy(bits.Scan0, buf, 0, buf.Length);
      bmp.UnlockBits(bits);
      int best = 0, bestX = 0, bestY = 0;
      int y0 = (int)(h * 0.55);
      for (int y = y0; y < h - 2; y += 2) {
        int len = 0, start = 0;
        for (int x = 0; x < w; x += 2) {
          int i = y * stride + x * 4;
          int b = buf[i], gch = buf[i + 1], red = buf[i + 2];
          bool orange = red > 200 && gch > 70 && gch < 220 && b < 120 && red > b + 80;
          if (orange) {
            if (len == 0) start = x;
            len += 2;
          } else if (len > 0) {
            if (len > best) { best = len; bestX = start + len / 2; bestY = y; }
            len = 0;
          }
        }
        if (len > best) { best = len; bestX = start + len / 2; bestY = y; }
      }
      if (best < 120) return false;
      absX = rect.Left + bestX;
      absY = rect.Top + bestY;
      run = best;
      return true;
    }
  }
}
"@
[void][WgStart]::SetProcessDPIAware()
$log = Join-Path $env:TEMP 'xiaoke-wegame-start.log'
function Click-Start {
  $hwnd = [WgStart]::Find()
  if ($hwnd -eq [IntPtr]::Zero) { Add-Content $log 'NO_WINDOW'; return $false }
  [void][WgStart]::ShowWindow($hwnd, 9)
  [void][WgStart]::SetWindowPos($hwnd, [IntPtr](-1), 0, 0, 0, 0, 0x0043)
  [void][WgStart]::SetForegroundWindow($hwnd)
  Start-Sleep -Milliseconds 700
  $x = 0; $y = 0; $run = 0
  $ok = [WgStart]::Locate($hwnd, [ref]$x, [ref]$y, [ref]$run)
  if (-not $ok) {
    [void][WgStart]::SetWindowPos($hwnd, [IntPtr](-2), 0, 0, 0, 0, 0x0043)
    Add-Content $log 'NO_BUTTON'
    return $false
  }
  Add-Content $log "CLICK $x $y run=$run"
  [void][WgStart]::SetCursorPos($x, $y)
  [WgStart]::mouse_event(0x0002, 0, 0, 0, 0)
  [WgStart]::mouse_event(0x0004, 0, 0, 0, 0)
  Start-Sleep -Milliseconds 200
  [void][WgStart]::SetWindowPos($hwnd, [IntPtr](-2), 0, 0, 0, 0, 0x0043)
  return $true
}
Start-Sleep -Seconds 2
foreach ($try in 1..8) {
  if (Click-Start) { exit 0 }
  Start-Sleep -Seconds 2
}
exit 4
"""


def _load_shortcuts() -> list[Shortcut]:
    """开始菜单和桌面是安装程序自己写的，路径不写死。"""
    if os.name != "nt":
        return []
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$sh = New-Object -ComObject WScript.Shell
$roots = @(
  [Environment]::GetFolderPath('Programs'),
  [Environment]::GetFolderPath('CommonPrograms'),
  [Environment]::GetFolderPath('Desktop'),
  [Environment]::GetFolderPath('CommonDesktopDirectory')
)
$rows = New-Object System.Collections.Generic.List[object]
foreach ($root in $roots) {
  if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
  Get-ChildItem -LiteralPath $root -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
    $s = $sh.CreateShortcut($_.FullName)
    $rows.Add([pscustomobject]@{
      name = $_.BaseName
      target = [string]$s.TargetPath
      args = [string]$s.Arguments
      workdir = [string]$s.WorkingDirectory
    })
  }
}
if ($rows.Count -eq 0) { '[]' } else { $rows | ConvertTo-Json -Compress }
"""
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    raw = (done.stdout or "").strip()
    if not raw:
        return []
    import json
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    found: list[Shortcut] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "").strip()
        if not target:
            continue
        found.append(Shortcut(
            name=str(item.get("name") or ""),
            target=target,
            args=str(item.get("args") or ""),
            workdir=str(item.get("workdir") or ""),
        ))
    return found


def _processes() -> list[Proc]:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    TH32CS_SNAPPROCESS = 0x00000002
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL

    snap = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value:
        return []
    found: list[Proc] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            name = str(entry.szExeFile or "")
            exe = _image_path(kernel, int(entry.th32ProcessID), PROCESS_QUERY_LIMITED_INFORMATION)
            found.append(Proc(name=name, exe=exe))
            ok = kernel.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snap)
    return found


def _image_path(kernel, pid: int, access: int) -> str:
    import ctypes
    from ctypes import wintypes

    handle = kernel.OpenProcess(access, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value
    finally:
        kernel.CloseHandle(handle)


_HOST: WindowsHost | None = None


def get_host() -> WindowsHost:
    global _HOST
    if _HOST is None:
        _HOST = WindowsHost()
    return _HOST


def set_host(host: WindowsHost | None) -> None:
    global _HOST
    _HOST = host
