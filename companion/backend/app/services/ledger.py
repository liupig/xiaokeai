"""把记账交给单独的进程。聊天只把任务放进去，不等它写完。

这是本机的一条队列，不另起 Redis。加密重放在子进程里，不会冻住语音。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Optional

from .coins_box import CoinError

_ROOT = Path(__file__).resolve().parents[2]
_proc: Optional[subprocess.Popen] = None
_write_lock = threading.Lock()
_start_lock = threading.Lock()
_pending: dict[int, Queue] = {}
_forget: set[int] = set()
_seq = 0
_seq_lock = threading.Lock()


def start() -> None:
    global _proc
    with _start_lock:
        if _proc is not None and _proc.poll() is None:
            return
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        _proc = subprocess.Popen(
            [sys.executable, "-m", "app.services.ledger_proc"],
            cwd=str(_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=_read, args=(_proc,), daemon=True, name="ledger-reader").start()


def stop() -> None:
    global _proc
    proc = _proc
    _proc = None
    if proc is None or proc.poll() is not None:
        return
    try:
        if proc.stdin:
            proc.stdin.close()
    except OSError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


def call(op: str, args: Optional[list] = None, timeout: float = 30) -> Any:
    msg = _send(op, args, wait=True, timeout=timeout)
    if not msg.get("ok"):
        raise CoinError(str(msg.get("error") or "busy"))
    return msg.get("result")


def enqueue(op: str, args: Optional[list] = None) -> None:
    """放进账本进程就返回。聊天和语音不看这一笔有没有写完。"""
    try:
        _send(op, args, wait=False)
    except Exception as exc:
        print(f"[coins] enqueue {op} skipped: {exc}", file=sys.stderr)


def _send(op: str, args: Optional[list], wait: bool, timeout: float = 30) -> dict:
    start()
    proc = _proc
    if proc is None or proc.poll() is not None or proc.stdin is None:
        raise CoinError("busy")
    with _seq_lock:
        global _seq
        _seq += 1
        ident = _seq
    box: Queue = Queue(maxsize=1)
    _pending[ident] = box
    if not wait:
        _forget.add(ident)
    line = json.dumps({"id": ident, "op": op, "args": list(args or [])}, ensure_ascii=False)
    with _write_lock:
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
    if not wait:
        return {"id": ident, "ok": True, "result": None}
    try:
        return box.get(timeout=timeout)
    except Empty:
        _pending.pop(ident, None)
        raise CoinError("busy")
    finally:
        _pending.pop(ident, None)


def _read(proc: subprocess.Popen) -> None:
    stdout = proc.stdout
    if stdout is None:
        return
    for line in stdout:
        text = line.strip()
        if not text:
            continue
        try:
            msg = json.loads(text)
            ident = int(msg.get("id") or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            print(f"[coins] bad ledger line: {text[:120]}", file=sys.stderr)
            continue
        if ident in _forget:
            _forget.discard(ident)
            _pending.pop(ident, None)
            if not msg.get("ok"):
                print(f"[coins] job {ident} skipped: {msg.get('error')}", file=sys.stderr)
            continue
        box = _pending.get(ident)
        if box is not None:
            box.put(msg)
