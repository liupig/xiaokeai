"""开游戏的指令，和查这次有没有开成的网址。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ...db import get_session
from ...services import settings_store
from ..flags import enabled
from . import service

router = APIRouter(prefix="/api/modules/play", tags=["modules-play"])


def _guard(session: Session) -> None:
    if not enabled(session, "play"):
        raise HTTPException(404, "play module off")


def _region(session: Session, explicit: str) -> str:
    raw = (explicit or "").strip().lower()
    if raw in {"cn", "china", "zh", "zh-cn"}:
        return "cn"
    if raw in {"intl", "global", "oversea", "overseas"}:
        return "intl"
    locale = ((settings_store.get_all(session).get("locale") or {}).get("ui") or "")
    if str(locale).lower().startswith("zh"):
        return "cn"
    return "intl"


def _with_url(job: dict[str, Any], request: Request) -> dict[str, Any]:
    out = dict(job)
    path = str(job.get("status_url") or "")
    if path:
        out["status_url"] = str(request.base_url).rstrip("/") + path
    return out


class OpenIn(BaseModel):
    game: str = ""
    platform: str = ""
    region: str = ""


@router.get("/launchers")
def list_launchers(session: Session = Depends(get_session)) -> dict[str, Any]:
    _guard(session)
    return service.launchers()


@router.get("/library")
def list_library(region: str = "", session: Session = Depends(get_session)) -> dict[str, Any]:
    _guard(session)
    return service.installed(region=_region(session, region))


@router.post("/open")
def open_game(body: OpenIn, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    _guard(session)
    if not (body.game or "").strip() and not (body.platform or "").strip():
        raise HTTPException(400, "game required")
    job = service.open_game(
        body.game,
        platform=body.platform,
        region=_region(session, body.region),
    )
    return _with_url(job, request)


@router.get("/jobs/{job_id}")
def job_status(job_id: str, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    _guard(session)
    job = service.job_status(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    return _with_url(job, request)
