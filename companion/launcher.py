#coding=utf-8
"""Companion Studio 桌面启动器：同时拉起后端 API、前端页面和内嵌 Chromium 窗口。

开发环境端口：前端 5175、后端 8600。
打包环境端口：前端 9615、后端 9610，避免和本机开发抢端口。
窗口内核是 Electron 自带的 Chromium，不需要本机安装 Chrome。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import traceback
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

HOST = "127.0.0.1"
BACKEND_PORT = 9610
FRONTEND_PORT = 9615
HEALTH = f"http://{HOST}:{BACKEND_PORT}/api/health"
HOME = f"http://{HOST}:{FRONTEND_PORT}/"


def root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).resolve().parent


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((HOST, port)) == 0


def wait_url(url: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (URLError, OSError, TimeoutError):
            time.sleep(0.4)
    return False


def kill_tree(pid: int) -> bool:
    pid = int(pid or 0)
    if pid <= 0:
        return False
    r = subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return r.returncode == 0


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.pid:
        kill_tree(proc.pid)
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def _cim_processes() -> list[dict]:
    ps = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            timeout=25,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return []
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for row in data or []:
        try:
            out.append({
                "pid": int(row.get("ProcessId") or 0),
                "exe": str(row.get("ExecutablePath") or ""),
            })
        except (TypeError, ValueError):
            continue
    return out


def apply_dotenv(root: Path) -> int:
    """把发行目录旁的 .env 灌进进程环境，后端子进程会继承。不覆盖已有系统变量。"""
    n = 0
    for path in (root / ".env", root / "data" / ".env", root / "scripts" / ".env"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val and not (os.environ.get(key) or "").strip():
                os.environ[key] = val
                n += 1
    return n


def reap_same_python(python: Path) -> int:
    want = str(python.resolve()).lower()
    me = os.getpid()
    n = 0
    for row in _cim_processes():
        pid = row["pid"]
        if pid <= 0 or pid == me:
            continue
        exe = (row["exe"] or "").replace("/", "\\").lower()
        try:
            exe = str(Path(row["exe"]).resolve()).lower() if row["exe"] else ""
        except OSError:
            pass
        if exe != want:
            continue
        if kill_tree(pid):
            n += 1
            print(f"已结束残留 pid={pid}")
    return n


def pid_on_port(port: int) -> int:
    try:
        raw = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True, errors="replace", timeout=8,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return 0
    want = str(int(port))
    for line in raw.splitlines():
        if "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if len(parts) < 5 or not parts[-1].isdigit():
            continue
        _host, _, p = parts[1].rpartition(":")
        if p == want:
            return int(parts[-1])
    return 0


def reap_port(port: int) -> bool:
    pid = pid_on_port(port)
    if pid <= 0 or pid == os.getpid():
        return False
    print(f"端口 {port} 被 pid={pid} 占用，正在结束…")
    return kill_tree(pid)


class WinJob:
    """关掉本窗口（含崩溃）时，系统会杀掉作业里的前后端和 TTS 子进程。"""

    def __init__(self) -> None:
        self.handle = None
        self._k32 = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
        except (ImportError, OSError):
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(info), ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(job)
            return
        self._k32 = kernel32
        self.handle = job

    def add(self, pid: int) -> bool:
        if not self.handle or not self._k32 or pid <= 0:
            return False
        access = 0x0001 | 0x0100 | 0x0200
        h = self._k32.OpenProcess(access, False, int(pid))
        if not h:
            return False
        try:
            return bool(self._k32.AssignProcessToJobObject(self.handle, h))
        finally:
            self._k32.CloseHandle(h)


def open_shell(
    root: Path, home: str, job: WinJob, path_system: str,
) -> subprocess.Popen | None:
    """拉起打包进来的 Electron/Chromium。PATH 只用系统路径，避免撞上 Python 的 DLL。"""
    exe = root / "electron" / "electron.exe"
    if not exe.is_file():
        print(f"找不到内嵌 Chromium：{exe}")
        return None
    env = os.environ.copy()
    env["PATH"] = str(exe.parent) + os.pathsep + path_system
    env["COMPANION_HOME"] = home
    args = [str(exe)]
    bundled = exe.parent / "resources" / "app" / "main.js"
    sidecar = root / "desktop"
    if not bundled.is_file() and (sidecar / "main.js").is_file():
        args.append(str(sidecar))
    print("正在打开内嵌 Chromium 窗口…")
    proc = subprocess.Popen(args, cwd=str(exe.parent), env=env)
    job.add(proc.pid)
    return proc


def main() -> int:
    root = root_dir()
    runtime = root / "runtime"
    python = runtime / "python.exe"
    if not python.is_file():
        print(f"找不到运行时：{python}")
        print("请使用 build_exe.py 打包后再运行。")
        input("按回车退出…")
        return 1

    lib_bin = runtime / "Library" / "bin"
    torch_lib = runtime / "Lib" / "site-packages" / "torch" / "lib"
    path_parts = [str(runtime), str(lib_bin), str(runtime / "Scripts"), str(torch_lib)]
    nvidia = runtime / "Lib" / "site-packages" / "nvidia"
    if nvidia.is_dir():
        for p in nvidia.glob("*/bin"):
            path_parts.append(str(p))
        for p in nvidia.glob("*/lib"):
            path_parts.append(str(p))
    path_system = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(path_parts + [path_system])
    os.environ["COMPANION_ROOT"] = str(root)
    os.environ["COMPANION_BACKEND"] = f"http://{HOST}:{BACKEND_PORT}"
    os.environ["PYTHONPATH"] = str(root)
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
    os.environ["MEM0_TELEMETRY"] = "False"
    os.environ["PYTHONWARNINGS"] = "ignore:Failed to find:UserWarning"
    env_n = apply_dotenv(root)
    if env_n:
        model = os.environ.get("COMPANION_LLM_MODEL") or ""
        has_key = bool(
            (os.environ.get("COMPANION_LLM_API_KEY") or os.environ.get("ARK_API_KEY") or "").strip()
        )
        print(f"已加载本地 .env（LLM key={'有' if has_key else '无'}"
              f"{' · ' + model if model else ''}）")

    print("=" * 56)
    print("  Companion Studio  打包版（窗口 + 前端 + 后端）")
    print("=" * 56)
    print(f"目录：{root}")
    print(f"后端 API  http://{HOST}:{BACKEND_PORT}   （开发环境是 8600）")
    print(f"前端页面  http://{HOST}:{FRONTEND_PORT}   （开发环境是 5175）")
    print()

    try:
        n = reap_same_python(python)
        if n:
            print(f"已清理上次残留进程 {n} 个（含 GPU 子进程）")
            time.sleep(0.6)
    except Exception as exc:
        print(f"清理残留进程时出错（继续启动）：{exc}")

    for name, port in (("后端", BACKEND_PORT), ("前端", FRONTEND_PORT)):
        if port_busy(port):
            try:
                reap_port(port)
                time.sleep(0.4)
            except Exception:
                pass
        if port_busy(port):
            print(f"{name}端口 {port} 已被占用，打包版起不来。")
            print("请关掉占用该端口的程序后再双击。开发环境的 5175/8600 可以继续开着。")
            input("按回车退出…")
            return 1

    job = WinJob()
    backend = None
    frontend = None
    desktop = None
    backend = subprocess.Popen(
        [
            str(python), "-m", "uvicorn", "app.main:app",
            "--host", HOST, "--port", str(BACKEND_PORT), "--log-level", "info",
        ],
        cwd=str(root),
    )
    job.add(backend.pid)
    try:
        print("正在启动后端…")
        if not wait_url(HEALTH):
            print("后端启动超时。请看上方日志。")
            input("按回车退出…")
            return 1
        print(f"后端已就绪  {HEALTH}")

        print("正在启动前端…")
        frontend = subprocess.Popen(
            [
                str(python), "-m", "uvicorn", "app.pack_web:app",
                "--host", HOST, "--port", str(FRONTEND_PORT), "--log-level", "warning",
            ],
            cwd=str(root),
        )
        job.add(frontend.pid)
        if not wait_url(HOME):
            print("前端启动超时。请看上方日志。")
            input("按回车退出…")
            return 1
        print(f"前端已就绪  {HOME}")

        desktop = open_shell(root, HOME, job, path_system)
        if desktop is None:
            print("正在打开系统浏览器（未找到内嵌 Chromium）…")
            webbrowser.open(HOME)
            print("关掉本窗口即退出前后端（含 TTS 占用的显存）。")
        else:
            print("已打开内嵌 Chromium 窗口（不需要安装 Chrome）。")
            print("关掉窗口或本黑窗即退出（含 TTS 占用的显存）。")
        while True:
            if desktop is not None and desktop.poll() is not None:
                print("窗口已关闭")
                break
            if backend.poll() is not None:
                print(f"后端已退出，代码 {backend.returncode}")
                break
            if frontend.poll() is not None:
                print(f"前端已退出，代码 {frontend.returncode}")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在退出…")
    finally:
        stop(desktop)
        stop(frontend)
        stop(backend)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        try:
            input("启动失败，按回车退出…")
        except Exception:
            time.sleep(8)
        code = 1
    sys.exit(code)
