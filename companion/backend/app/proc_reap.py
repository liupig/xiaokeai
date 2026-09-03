"""清理本程序拉起的 Python / GPU 子进程。

打包版：runtime\\python.exe 整棵进程树都算「自己人」。
开发版：只动当前这个 python.exe，且只杀无主的 multiprocessing 子进程、
        以及本仓库的 uvicorn，避免误伤同环境里别的程序。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable


def kill_tree(pid: int) -> bool:
    """Windows：连子孙一起杀。其它平台：terminate 再 kill。"""
    pid = int(pid or 0)
    if pid <= 0 or pid == os.getpid():
        return False
    if os.name == "nt":
        r = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return r.returncode == 0
    try:
        os.kill(pid, 15)
    except OSError:
        return False
    for _ in range(20):
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    try:
        os.kill(pid, 9)
    except OSError:
        return False
    return True


def pid_alive(pid: int) -> bool:
    pid = int(pid or 0)
    if pid <= 0:
        return False
    if os.name == "nt":
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, check=False,
        )
        return str(pid) in (r.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _norm(p: str | Path | None) -> str:
    if not p:
        return ""
    try:
        return str(Path(p).resolve()).lower()
    except OSError:
        return str(p).replace("/", "\\").lower()


def iter_processes() -> list[dict]:
    if os.name != "nt":
        return []
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
                "ppid": int(row.get("ParentProcessId") or 0),
                "exe": str(row.get("ExecutablePath") or ""),
                "cmd": str(row.get("CommandLine") or ""),
            })
        except (TypeError, ValueError):
            continue
    return out


def _is_our_python(exe: str, ours: str) -> bool:
    a, b = _norm(exe), _norm(ours)
    return bool(a and b and a == b)


def _is_mp_fork(cmd: str) -> bool:
    c = (cmd or "").lower()
    return "multiprocessing.spawn" in c or "--multiprocessing-fork" in c


def _is_our_uvicorn(cmd: str) -> bool:
    c = (cmd or "").lower()
    return "uvicorn" in c and (
        "app.main:app" in c or "app.pack_web:app" in c
    )


def reap_same_python(python: Path, keep: Iterable[int] | None = None) -> int:
    """杀掉指定 python.exe 的残留实例（打包版 runtime 专用）。"""
    keep_set = {os.getpid(), *(int(x) for x in (keep or []) if x)}
    ours = str(python)
    n = 0
    for row in iter_processes():
        pid = row["pid"]
        if pid in keep_set or pid <= 0:
            continue
        if not _is_our_python(row["exe"], ours):
            continue
        if kill_tree(pid):
            n += 1
            print(f"[proc] killed leftover pid={pid}")
    return n


def reap_dead_workers(python: Path | None = None) -> int:
    """杀掉「父进程已死」的 multiprocessing 子进程（开发/打包都适用）。"""
    ours = str(python or sys.executable)
    keep = os.getpid()
    alive = {row["pid"] for row in iter_processes() if row["pid"]}
    n = 0
    for row in iter_processes():
        pid = row["pid"]
        if pid == keep or pid <= 0:
            continue
        if not _is_our_python(row["exe"], ours):
            continue
        parent_dead = row["ppid"] not in alive
        if _is_mp_fork(row["cmd"]) and parent_dead:
            if kill_tree(pid):
                n += 1
                print(f"[proc] killed orphan worker pid={pid}")
    return n


def pid_on_port(port: int) -> int:
    if os.name != "nt":
        return 0
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
        local = parts[1]
        host, _, p = local.rpartition(":")
        if p == want:
            return int(parts[-1])
    return 0


def reap_port(port: int) -> bool:
    pid = pid_on_port(port)
    if pid <= 0 or pid == os.getpid():
        return False
    print(f"[proc] port {port} held by pid={pid}, killing tree")
    return kill_tree(pid)


def shutdown_workers() -> None:
    """让 TTS / ASR / 记忆进程先走正常退出。"""
    try:
        from .services import tts_qwen
        tts_qwen._stop_worker()
    except Exception:
        pass
    try:
        from .services import asr
        asr._stop_worker()
    except Exception:
        pass
    try:
        from .modules.memory import worker as memory_worker
        memory_worker._stop()
    except Exception:
        pass


def reap_children(parent_pid: int | None = None) -> int:
    parent = int(parent_pid or os.getpid())
    n = 0
    for row in iter_processes():
        if row["ppid"] == parent and row["pid"] != parent:
            if kill_tree(row["pid"]):
                n += 1
    return n


class WinJob:
    """父进程退出（含崩溃）时，操作系统会杀掉作业里所有进程。"""

    def __init__(self) -> None:
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

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

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JobObjectExtendedLimitInformation = 9
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(job)
            return
        self._k32 = kernel32
        self.handle = job

    def add(self, pid: int) -> bool:
        if not self.handle or pid <= 0:
            return False
        import ctypes
        PROCESS_TERMINATE = 0x0001
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_SET_INFORMATION = 0x0200
        access = PROCESS_TERMINATE | PROCESS_SET_QUOTA | PROCESS_SET_INFORMATION
        h = self._k32.OpenProcess(access, False, int(pid))
        if not h:
            return False
        try:
            return bool(self._k32.AssignProcessToJobObject(self.handle, h))
        finally:
            self._k32.CloseHandle(h)
