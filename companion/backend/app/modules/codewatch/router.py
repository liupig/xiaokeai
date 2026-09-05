"""Code 伴侣 API：开监视、收 hook、推 SSE。"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ...db import get_session
from ..flags import enabled
from . import hooks
from .service import bus
from .watch import cursor_home_ok, watch

router = APIRouter(prefix="/api/modules/codewatch", tags=["modules-codewatch"])


def _guard(session: Session) -> None:
    if not enabled(session, "codewatch"):
        raise HTTPException(404, "codewatch module off")


def _ports() -> list[int]:
    raw = os.environ.get("COMPANION_BACKEND_PORT") or ""
    extra: list[int] = []
    if raw.isdigit():
        extra.append(int(raw))
    return extra + [8600, 5201]


@router.get("/status")
def status(session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    if not bus.snapshot().get("watching"):
        bus.refresh_found()
    snap = bus.snapshot()
    snap["cursor_home"] = cursor_home_ok()
    snap["hooks"] = hooks.status()
    return snap


class WatchIn(BaseModel):
    sources: List[str] = []


@router.post("/watch/start")
def watch_start(body: WatchIn | None = None, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    hooks.write_hint(_ports())
    bus.set_enabled((body or WatchIn()).sources)
    snap = bus.set_watching(True)
    watch.start()
    snap["cursor_home"] = cursor_home_ok()
    snap["hooks"] = hooks.status()
    return snap


@router.post("/watch/sources")
def watch_sources(body: WatchIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    bus.set_enabled(body.sources)
    snap = bus.snapshot()
    snap["cursor_home"] = cursor_home_ok()
    snap["hooks"] = hooks.status()
    return snap


@router.post("/watch/stop")
def watch_stop(session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    watch.stop()
    snap = bus.set_watching(False)
    snap["cursor_home"] = cursor_home_ok()
    snap["hooks"] = hooks.status()
    return snap


@router.get("/hooks")
def hooks_get(session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return hooks.status()


@router.post("/hooks/install")
def hooks_install(session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return hooks.install(_ports())


@router.post("/hooks/uninstall")
def hooks_uninstall(session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return hooks.uninstall()


@router.post("/hook")
async def hook_ingest(request: Request) -> Dict[str, Any]:
    """Cursor hook 回传。模块关着也 200，避免钩子失败挡对话。"""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if not bus.snapshot().get("watching"):
        return {"ok": True, "applied": False, "reason": "not-watching"}
    return hooks.ingest(payload)


@router.get("/events")
async def events(session: Session = Depends(get_session)):
    _guard(session)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue(maxsize=32)

    def push(snap: Dict[str, Any]) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, snap)
        except Exception:
            pass

    bus.subscribe(push)

    async def gen():
        try:
            yield _sse(bus.snapshot())
            while True:
                try:
                    snap = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keep\n\n"
                    continue
                if snap is None:
                    break
                yield _sse(snap)
        finally:
            bus.unsubscribe(push)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(payload: Dict[str, Any]) -> str:
    import json
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def release() -> None:
    watch.stop()
    bus.set_watching(False)
