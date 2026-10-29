"""抖音直播弹幕。网页直播间和开放平台回调进同一个收件箱。"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import Session

from ....db import get_session
from ....services import settings_store
from ...flags import enabled
from . import inbox, listen
from .sign import signature_ok

router = APIRouter(prefix="/api/modules/live/douyin", tags=["modules-live-douyin"])


class ListenBody(BaseModel):
    room: str = ""


def _guard(session: Session) -> None:
    if not enabled(session, "live_douyin"):
        raise HTTPException(404, "live module off")


def _secret(session: Session) -> str:
    live = settings_store.get_all(session).get("live") or {}
    douyin = live.get("douyin") if isinstance(live, dict) else {}
    if not isinstance(douyin, dict):
        return ""
    return str(douyin.get("push_secret") or "")


@router.get("/feed")
def feed(after: int = 0, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    snap = listen.snapshot()
    items = inbox.since(after)
    return {**snap, "items": items}


@router.post("/listen")
def listen_start(body: ListenBody, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    room = (body.room or "").strip()
    if not room:
        raise HTTPException(400, "先填直播间链接或房间号")
    return listen.start(room)


@router.post("/stop")
def listen_stop(session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return listen.stop()


@router.post("/callback")
async def callback(request: Request, session: Session = Depends(get_session)):
    """抖音开放平台把评论、礼物、点赞 POST 到这里。2xx 才算收下。"""
    _guard(session)
    raw = await request.body()
    body = raw.decode("utf-8", "replace")
    headers = {k.lower(): v for k, v in request.headers.items()}
    secret = _secret(session)
    if secret and not signature_ok(headers, body, secret):
        return JSONResponse({"err_no": 1, "err_msg": "bad signature"}, status_code=401)
    accepted = inbox.accept_callback(headers.get("x-msg-type") or "", body, headers.get("x-roomid") or "")
    return {"err_no": 0, "err_msg": "ok", "accepted": accepted}
