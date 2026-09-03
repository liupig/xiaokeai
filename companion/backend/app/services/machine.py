"""探测本机内存 / 显存 / CPU。不 import torch，避免拖垮启动。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any, Dict


def _ram_gb() -> float:
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024 ** 3), 1)
        except Exception:
            pass
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        phys = os.sysconf("SC_PHYS_PAGES")
        return round(page * phys / (1024 ** 3), 1)
    except (AttributeError, ValueError, OSError):
        pass
    try:
        text = open("/proc/meminfo", encoding="utf-8").read()
        for line in text.splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                return round(kb / (1024 ** 2), 1)
    except OSError:
        pass
    return 0.0


def _vram_gb() -> float:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return 0.0
    kwargs: Dict[str, Any] = {
        "args": [
            smi,
            "--query-gpu=memory.total",
            "--format=csv,noheader,nounits",
        ],
        "capture_output": True,
        "text": True,
        "timeout": 4,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(**kwargs)
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    if out.returncode != 0:
        return 0.0
    best = 0.0
    for line in (out.stdout or "").splitlines():
        try:
            mb = float(line.strip().split()[0])
        except (ValueError, IndexError):
            continue
        best = max(best, mb / 1024.0)
    return round(best, 1)


def probe() -> Dict[str, Any]:
    ram = _ram_gb()
    vram = _vram_gb()
    cores = int(os.cpu_count() or 2)
    fp = f"{round(ram * 2) / 2:.1f}:{round(vram * 2) / 2:.1f}:{cores}"
    return {
        "ram_gb": ram,
        "vram_gb": vram,
        "cores": cores,
        "fingerprint": fp,
    }
