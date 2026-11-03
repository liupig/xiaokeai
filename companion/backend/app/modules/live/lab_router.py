"""本机彩排 API。与正式直播模块开关、凭据和会话隔离。"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .lab import LiveLab
from .lab_journal import LabJournal
from .lab_scenarios import scenario_public

router = APIRouter(prefix="/api/live-lab", tags=["live-lab"])
_lab: LiveLab | None = None


def get_lab() -> LiveLab:
    global _lab
    if _lab is None:
        from ...paths import DATA_DIR
        _lab = LiveLab(LabJournal(DATA_DIR / "live-lab.sqlite3"))
    return _lab


def configured_llm() -> dict:
    from sqlmodel import Session
    from ...db import engine
    from ...services import settings_store
    with Session(engine) as session:
        return dict(settings_store.get_all(session).get("llm") or {})


class StartBody(BaseModel):
    scenario: str = "mixed"
    mode: Literal["scripted", "configured"] = "scripted"
    speed: float = Field(default=1, ge=.25, le=8)


class InjectBody(BaseModel):
    nickname: str = Field(default="我", min_length=1, max_length=24)
    content: str = Field(min_length=1, max_length=300)
    kind: Literal["comment", "gift", "superchat"] = "comment"
    gift: str = Field(default="小心心", max_length=24)
    count: int = Field(default=1, ge=1, le=1000)


class AckBody(BaseModel):
    turn_id: str
    outcome: Literal["completed", "displayed", "failed", "interrupted"]
    player_id: str = Field(default="", max_length=80)


class ClaimBody(BaseModel):
    turn_id: str
    player_id: str = Field(min_length=1, max_length=80)


class FaultBody(BaseModel):
    kind: Literal["model", "disconnect", "duplicate"]


class PauseBody(BaseModel):
    paused: bool


class RecoverBody(BaseModel):
    run_id: str


@router.get("/config")
def config():
    try:
        llm = configured_llm()
        ready = bool(llm.get("api_key") and llm.get("base_url"))
    except Exception:
        llm, ready = {}, False
    return {"scenarios": scenario_public(), "configured_model_ready": ready,
            "model": str(llm.get("model") or ""), "history": get_lab().journal.history()}


@router.post("/start")
def start(body: StartBody):
    try:
        return get_lab().start(body.scenario, body.mode, body.speed,
                               llm=configured_llm() if body.mode == "configured" else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/state")
def state(after: int = 0):
    return get_lab().snapshot(after)


@router.post("/stop")
def stop():
    get_lab().stop()
    return get_lab().snapshot()


@router.post("/pause")
def pause(body: PauseBody):
    try:
        get_lab().pause(body.paused)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/inject")
def inject(body: InjectBody):
    try:
        get_lab().inject(body.content, body.nickname, body.kind, body.gift, body.count)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/ack")
def ack(body: AckBody):
    return {"ok": get_lab().ack(body.turn_id, body.outcome, player_id=body.player_id)}


@router.post("/claim")
def claim(body: ClaimBody):
    return {"ok": get_lab().claim(body.turn_id, body.player_id)}


@router.post("/fault")
def fault(body: FaultBody):
    try:
        get_lab().fault(body.kind)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/report")
def report(run_id: str = ""):
    try:
        data = get_lab().report(run_id or None)
        return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="live-lab-{data["run_id"]}.json"'})
    except KeyError as exc:
        raise HTTPException(404, "彩排记录不存在") from exc


@router.post("/recover")
def recover(body: RecoverBody):
    try:
        mode = get_lab().journal.info(body.run_id)["mode"]
        return get_lab().recover_paid(body.run_id, llm=configured_llm() if mode == "configured" else None)
    except KeyError as exc:
        raise HTTPException(404, "彩排记录不存在") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
