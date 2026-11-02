"""直播总控。平台连接、开关、开播和舞台要念的一句都从这里走。"""
from __future__ import annotations

import time
from typing import Any
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from ...db import get_session
from ...services import settings_store
from ..flags import enabled
from .config import feature_on, merge_live
from .events import LiveEvent
from .host import host

router = APIRouter(prefix="/api/modules/live", tags=["modules-live"])


class OnBody(BaseModel):
    character_id: int = 0


class AckBody(BaseModel):
    turn_id: str = ""
    outcome: Literal["completed", "displayed", "interrupted", "failed"] = "completed"
    player_id: str = Field(default="", max_length=80)


class ClaimBody(BaseModel):
    turn_id: str
    player_id: str = Field(min_length=1, max_length=80)


class RehearsalBody(BaseModel):
    nickname: str = "彩排"
    content: str = ""
    kind: str = "comment"
    gift: str = ""
    count: int = 1


class CueBody(BaseModel):
    act: str = ""


def _guard(session: Session) -> None:
    if not enabled(session, "live"):
        raise HTTPException(404, "live module off")


def _save(session: Session, patch: dict) -> dict:
    current = settings_store.get_all(session).get("live")
    merged = merge_live(current, patch)
    settings_store.update(session, {"live": merged})
    return merged


@router.get("/desk")
def desk(busy: int = 0, character_id: int = 0, session: Session = Depends(get_session)) -> dict:
    _guard(session)
    host.note_busy(bool(busy), character_id)
    if host.on_air and not host.loop_alive() and feature_on(host.cfg(), "watchdog"):
        host.health.degraded = True
        host.health.note("主持循环停了，正在拉起")
        host.ensure_loop()
    return host.snapshot()


@router.post("/on")
def on_air(body: OnBody, session: Session = Depends(get_session)) -> dict:
    _guard(session)
    result = host.go_on(body.character_id)
    snap = host.snapshot()
    snap["ok"] = result["ok"]
    snap["missing"] = result["missing"]
    return snap


@router.post("/off")
def off_air(session: Session = Depends(get_session)) -> dict:
    _guard(session)
    host.go_off()
    snap = host.snapshot()
    snap["ok"] = True
    return snap


@router.post("/ack")
def ack(body: AckBody, session: Session = Depends(get_session)) -> dict:
    _guard(session)
    return {"ok": host.ack(body.turn_id, body.outcome, body.player_id)}


@router.post("/claim")
def claim(body: ClaimBody, session: Session = Depends(get_session)) -> dict:
    _guard(session)
    return {"ok": host.claim(body.turn_id, body.player_id)}


@router.put("/config")
def put_config(patch: dict[str, Any], session: Session = Depends(get_session)) -> dict:
    _guard(session)
    return {"ok": True, "live": _save(session, patch)}


@router.post("/bilibili/start")
def bili_start(session: Session = Depends(get_session)) -> dict:
    _guard(session)
    result = host.start_bilibili()
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "连接失败")
    return result


@router.post("/bilibili/stop")
def bili_stop(session: Session = Depends(get_session)) -> dict:
    _guard(session)
    return host.stop_bilibili()


@router.post("/budget/reset")
def budget_reset(session: Session = Depends(get_session)) -> dict:
    _guard(session)
    host.reset_budget()
    return host.snapshot()


@router.post("/rehearsal")
def rehearsal(body: RehearsalBody, session: Session = Depends(get_session)) -> dict:
    _guard(session)
    if not feature_on(host.cfg(), "rehearsal"):
        raise HTTPException(404, "rehearsal off")
    kind = body.kind if body.kind in ("comment", "gift", "superchat") else "comment"
    content = (body.content or "").strip()
    gift = (body.gift or "").strip()
    count = max(1, int(body.count or 1))
    if kind == "gift" and not content:
        content = f"送出 {gift or '礼物'}×{count}"
    if not content:
        raise HTTPException(400, "先写一句")
    ok = host.ingest(LiveEvent(
        "rehearsal", kind, body.nickname or "彩排", content,
        gift=gift, count=count, msg_id=f"reh-{time.time_ns()}",
    ))
    return {"ok": bool(ok)}


@router.post("/cue")
def cue(body: CueBody, session: Session = Depends(get_session)) -> dict:
    _guard(session)
    if not feature_on(host.cfg(), "commands"):
        raise HTTPException(404, "commands off")
    return {"ok": bool(host.push_cue(body.act))}
