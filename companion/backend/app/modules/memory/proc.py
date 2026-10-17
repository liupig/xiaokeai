"""记忆抽取独立进程：Mem0 / MiniLM / LLM infer 都在这里，不进 FastAPI。"""
from __future__ import annotations

import os
import queue
import threading
import traceback


def main(in_q, out_q) -> None:
    os.environ["COMPANION_MEM_WORKER"] = "1"
    os.environ["MEM0_TELEMETRY"] = "False"
    from app.infer_runtime import prepare_worker
    prepare_worker("memory")
    try:
        from app.db import engine, init_db
        from sqlmodel import Session

        from app.modules.memory.service import _patch_mem0_optional, warmup
        _patch_mem0_optional()

        init_db()
        with Session(engine) as session:
            warmup(session)
        out_q.put(("ready", "", None))
    except Exception as exc:
        out_q.put(("boot-err", "", f"{exc}\n{traceback.format_exc()}"))
        return

    extract_q: queue.Queue = queue.Queue()
    pending: set[int] = set()
    pending_lock = threading.Lock()

    def extract_loop() -> None:
        from app.modules.memory.extract import run_extract_job

        while True:
            cid = extract_q.get()
            if cid is None:
                break
            try:
                run_extract_job(int(cid))
            except Exception as exc:
                print(f"[memory] extract job failed cid={cid}: {exc}")
            finally:
                with pending_lock:
                    pending.discard(int(cid))

    threading.Thread(target=extract_loop, daemon=True, name="memory-extract").start()

    while True:
        try:
            cmd = in_q.get()
        except (EOFError, OSError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        kind = cmd[0]
        if kind == "stop":
            extract_q.put(None)
            break
        job_id = cmd[1] if len(cmd) > 1 else ""
        payload = cmd[2] if len(cmd) > 2 else None
        try:
            if kind == "extract":
                cid = int(payload)
                with pending_lock:
                    if cid in pending:
                        continue
                    pending.add(cid)
                extract_q.put(cid)
                continue
            if kind == "reload":
                from sqlmodel import Session as DbSession

                from app.db import engine
                from app.modules.memory.service import reset_client, warmup

                try:
                    reset_client()
                    with DbSession(engine) as session:
                        warmup(session)
                except Exception as exc:
                    print(f"[memory] reload failed: {exc}")
                continue
            result = _dispatch(kind, payload)
            out_q.put(("ok", job_id, result))
        except Exception as exc:
            out_q.put(("err", job_id, f"{exc}\n{traceback.format_exc()}"))


def _dispatch(kind: str, payload):
    from sqlmodel import Session

    from app.db import engine
    from app.modules.memory import service

    if kind == "inject":
        cid, messages = payload
        with Session(engine) as session:
            return service.inject_memory(session, int(cid), messages)
    if kind == "search":
        cid, query = payload
        with Session(engine) as session:
            return service.retrieve_facts(session, int(cid), str(query or ""))
    if kind == "list":
        with Session(engine) as session:
            return service.list_facts(session, int(payload))
    if kind == "upsert":
        with Session(engine) as session:
            return service.upsert_fact(session, **payload)
    if kind == "delete":
        cid, fact_id = payload
        with Session(engine) as session:
            return service.delete_fact(session, int(cid), str(fact_id))
    if kind == "scene_hints":
        with Session(engine) as session:
            return service.scene_hints(session, int(payload))
    if kind == "list_pins":
        with Session(engine) as session:
            return service.list_pins(session, int(payload))
    if kind == "pin":
        with Session(engine) as session:
            try:
                return service.pin_message(
                    session, int(payload["character_id"]), int(payload["message_id"]),
                )
            except KeyError:
                return {"error": "missing"}
            except ValueError as exc:
                return {"error": str(exc)}
    if kind == "unpin":
        cid, pin_id = payload
        with Session(engine) as session:
            return service.delete_pin(session, int(cid), str(pin_id))
    if kind == "list_episodes":
        with Session(engine) as session:
            return service.list_episodes(session, int(payload))
    if kind == "delete_episode":
        cid, episode_id = payload
        with Session(engine) as session:
            return service.delete_episode(session, int(cid), str(episode_id))
    raise RuntimeError(f"unknown memory cmd {kind}")
