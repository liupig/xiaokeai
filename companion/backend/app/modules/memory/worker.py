"""FastAPI 侧：把记忆读写丢给独立进程，抽取只投递不排队等。"""
from __future__ import annotations

import atexit
import multiprocessing as mp
import os
import threading
import time
import uuid
from typing import Any, Dict, List

_ctx = mp.get_context("spawn")
_lock = threading.Lock()
_rpc_lock = threading.Lock()
_in_q = None
_out_q = None
_proc = None
_boot_failed = False
_boot_error = ""


def _in_worker() -> bool:
    return os.environ.get("COMPANION_MEM_WORKER") == "1"


def _alive() -> bool:
    return bool(_proc is not None and _proc.is_alive())


def _stop() -> None:
    global _proc, _in_q, _out_q
    if _in_q is not None:
        try:
            _in_q.put(("stop", "", None))
        except Exception:
            pass
    if _proc is not None and _proc.is_alive():
        _proc.join(timeout=3)
        if _proc.is_alive():
            _proc.terminate()
    _proc = None
    _in_q = None
    _out_q = None


def release() -> None:
    """关掉记忆模块时卸掉向量库进程，避免低配机空占内存。"""
    global _boot_failed, _boot_error
    _stop()
    _boot_failed = True
    _boot_error = "memory module off"
    print("[memory] released worker")


def clear_boot_failed() -> None:
    global _boot_failed, _boot_error
    _boot_failed = False
    _boot_error = ""


def ensure() -> None:
    """拉起记忆进程并等 Mem0 ready。FastAPI 启动线程里调。"""
    global _proc, _in_q, _out_q, _boot_failed, _boot_error
    if _in_worker() or _alive():
        return
    if _boot_failed:
        raise RuntimeError(_boot_error or "记忆进程上次启动失败")
    with _lock:
        if _alive():
            return
        if _boot_failed:
            raise RuntimeError(_boot_error or "记忆进程上次启动失败")
        from .proc import main as mem_main
        _in_q = _ctx.Queue()
        _out_q = _ctx.Queue()
        _proc = _ctx.Process(target=mem_main, args=(_in_q, _out_q), daemon=True, name="companion-memory")
        _proc.start()
        try:
            kind, _, payload = _out_q.get(timeout=180)
        except Exception as exc:
            _stop()
            _boot_failed = True
            _boot_error = f"记忆进程启动超时：{exc}"
            raise RuntimeError(_boot_error) from exc
        if kind != "ready":
            _stop()
            _boot_failed = True
            _boot_error = f"记忆进程启动失败：{payload}"
            raise RuntimeError(_boot_error)
        print(f"[memory] worker pid={_proc.pid}")
        atexit.register(_stop)


def _rpc(kind: str, payload: Any, timeout: float = 30) -> Any:
    if _in_worker():
        from .proc import _dispatch
        return _dispatch(kind, payload)
    try:
        ensure()
    except Exception as exc:
        print(f"[memory] worker unavailable: {exc}")
        return None
    job = uuid.uuid4().hex
    deadline = time.time() + timeout
    with _rpc_lock:
        _in_q.put((kind, job, payload))
        while True:
            remain = deadline - time.time()
            if remain <= 0:
                raise TimeoutError("记忆进程超时")
            status, jid, body = _out_q.get(timeout=remain)
            if str(jid) != str(job):
                continue
            if status == "ok":
                return body
            if status == "err":
                raise RuntimeError(body)
            raise RuntimeError(f"记忆进程返回异常：{status}")


def tick(character_id: int) -> None:
    """有新 QA 就丢进抽取队列，不等结果；进程没起来就下次再说。"""
    if not character_id:
        return
    if _in_worker():
        from .extract import run_extract_job
        run_extract_job(int(character_id))
        return
    if not _alive() or _in_q is None:
        return
    _in_q.put(("extract", "", int(character_id)))


def inject_memory(character_id: int, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out = _rpc("inject", (int(character_id), list(messages)), timeout=12)
    return out if isinstance(out, list) else messages


def list_facts(character_id: int) -> List[Dict[str, Any]]:
    try:
        out = _rpc("list", int(character_id))
    except Exception as exc:
        print(f"[memory] list_facts failed: {exc}")
        return []
    return out if isinstance(out, list) else []


def upsert_fact(character_id: int, **kwargs) -> Dict[str, Any]:
    kwargs["character_id"] = int(character_id)
    out = _rpc("upsert", kwargs)
    return out if isinstance(out, dict) else {}


def delete_fact(character_id: int, fact_id: str) -> bool:
    return bool(_rpc("delete", (int(character_id), str(fact_id))))


def scene_hints(character_id: int) -> List[str]:
    out = _rpc("scene_hints", int(character_id))
    return out if isinstance(out, list) else []
