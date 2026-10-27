"""本机眼睛进程的开关。开着才占显存，关掉就把 8766 上的进程停掉。"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import httpx

from .service import eyes_url

_V47 = Path(__file__).resolve().parents[5] / "minicpm-o-demo" / "v47"
_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_log = None
_warm: threading.Thread | None = None
_job = None
_token = 0
_phase = "down"
_message = ""
_probe_at = 0.0
_probe_ok = False


def _local() -> bool:
    url = eyes_url()
    return "127.0.0.1" in url or "localhost" in url


def probe() -> bool:
    global _probe_at, _probe_ok
    if not _local():
        return True
    now = time.time()
    if now - _probe_at < 2:
        return _probe_ok
    ok = False
    try:
        resp = httpx.get(f"{eyes_url()}/api/status", timeout=1.5)
        ok = resp.status_code == 200
    except Exception:
        ok = False
    _probe_at = now
    _probe_ok = ok
    return ok


def eyes_status() -> dict:
    global _phase
    if not _local():
        return {"eyes": "remote", "message": ""}
    if probe():
        _phase = "up"
    elif _phase != "starting":
        _phase = "down"
    return {"eyes": _phase, "message": _message}


def _listeners(port: int) -> list[int]:
    try:
        raw = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, errors="replace")
    except Exception:
        return []
    found: list[int] = []
    for line in raw.splitlines():
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5 or not parts[1].endswith(f":{port}"):
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid > 0 and pid not in found:
            found.append(pid)
    return found


def _kill(pid: int) -> None:
    if pid <= 0:
        return
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def _bind(pid: int) -> None:
    """绑进本进程的作业。后端被结束时，操作系统会把视觉进程一起杀掉。"""
    global _job
    if not _local() or pid <= 0:
        return
    try:
        from ...proc_reap import WinJob
    except Exception:
        return
    if _job is None:
        _job = WinJob()
    try:
        _job.add(int(pid))
    except Exception:
        return


def bind_running() -> None:
    for pid in _listeners(8766):
        _bind(pid)


def _close_log(log) -> None:
    if log is None:
        return
    try:
        log.close()
    except Exception:
        return


def shutdown() -> None:
    """停掉本机眼睛。远程视觉只停陪看，不杀别人的机器。"""
    global _proc, _log, _warm, _token, _phase, _message, _probe_at, _probe_ok
    if not _local():
        return
    from .service import abort_eyes_calls

    with _lock:
        _token += 1
        proc = _proc
        warm = _warm
        log = _log
        _proc = None
        _warm = None
        _log = None
        _phase = "down"
        _message = ""
        _probe_at = 0.0
        _probe_ok = False
    abort_eyes_calls()
    if proc is not None and proc.poll() is None:
        _kill(proc.pid)
    for pid in _listeners(8766):
        _kill(pid)
    if proc is not None:
        try:
            proc.wait(timeout=3)
        except Exception:
            pass
    _close_log(log)
    if warm is not None and warm is not threading.current_thread() and warm.is_alive():
        warm.join(timeout=2)


def _warmup(token: int) -> None:
    global _phase, _message
    from .service import _borrow, _release

    for _ in range(90):
        if token != _token or _phase != "starting":
            return
        if probe():
            client = _borrow()
            try:
                client.post(f"{eyes_url()}/api/warmup", timeout=180)
            except Exception as exc:
                if token != _token or _phase != "starting":
                    return
                _message = str(exc)[:160]
            finally:
                _release(client)
            if token != _token or _phase != "starting":
                return
            if probe():
                bind_running()
                _phase = "up"
                _message = ""
            return
        time.sleep(1)
    if token == _token and _phase == "starting":
        _phase = "down"
        _message = "眼睛没有起来"


def ensure() -> str:
    """没在跑就拉起。已经在加载就不要再开一个。"""
    global _proc, _log, _warm, _token, _phase, _message
    if not _local():
        return "remote"
    if probe():
        bind_running()
        _phase = "up"
        _message = ""
        return "up"
    with _lock:
        if _phase == "starting" and _proc is not None and _proc.poll() is None:
            return "starting"
        py = Path(__import__("os").environ.get("XIAOKE_EYES_PYTHON") or (_V47 / ".venv" / "Scripts" / "python.exe"))
        app = _V47 / "app.py"
        if not py.is_file() or not app.is_file():
            _phase = "down"
            _message = "眼睛环境还没装好"
            return "missing"
        for pid in _listeners(8766):
            _kill(pid)
        _token += 1
        token = _token
        _phase = "starting"
        _message = ""
        _close_log(_log)
        _log = open(_V47 / "eyes-host.log", "a", encoding="utf-8")
        _proc = subprocess.Popen(
            [str(py), "app.py"],
            cwd=str(_V47),
            stdout=_log,
            stderr=_log,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        if _proc is not None:
            _bind(_proc.pid)
        _warm = threading.Thread(target=_warmup, args=(token,), name="eyes-warmup", daemon=True)
        _warm.start()
    return "starting"


def enable_glance() -> None:
    """文字或按钮打开视觉时，把功能许可一并打开，陪看循环才不会自己退出。"""
    try:
        from sqlmodel import Session

        from ...db import engine
        from ...services import settings_store

        with Session(engine) as session:
            current = dict(settings_store.get_all(session).get("modules") or {})
            if current.get("glance") is True:
                return
            current["glance"] = True
            settings_store.update(session, {"modules": current})
    except Exception:
        return
