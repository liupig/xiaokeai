"""塔罗发牌 API。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...db import get_session
from ..flags import enabled
from . import deck, plays, service

router = APIRouter(prefix="/api/modules/tarot", tags=["modules-tarot"])


def _guard(session: Session) -> None:
    if not enabled(session, "tarot"):
        raise HTTPException(404, "tarot module off")


class DrawIn(BaseModel):
    character_id: int
    spread: str = "daily"
    question: str = ""
    redeal: bool = False


class IntentIn(BaseModel):
    character_id: int
    text: str
    question: str = ""


class FocusIn(BaseModel):
    character_id: int
    index: Optional[int] = None


class DismissIn(BaseModel):
    character_id: int


class CutIn(BaseModel):
    character_id: int
    entropy: str = ""


class PickIn(BaseModel):
    character_id: int
    fan_index: int


class RevealIn(BaseModel):
    character_id: int
    index: int


class ClarifierIn(BaseModel):
    character_id: int
    host: Optional[int] = None


@router.get("/catalog")
def catalog(session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    cards = [deck.enrich(c) for c in deck.list_cards()]
    return {
        "back_url": "/assets/tarot/back.png",
        "back_ready": deck.back_exists(),
        "cards": cards,
        "art_count": sum(1 for c in cards if c.get("has_art")),
        "total": len(cards),
        "plays": plays.list_plays(),
    }


@router.get("/plays")
def list_plays(session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return {"plays": plays.list_plays()}


@router.get("/session/{character_id}")
def get_session_state(character_id: int, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.snapshot(character_id)


@router.post("/begin")
def begin(body: DrawIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    snap = service.begin(
        body.character_id, body.spread, body.question or "", redeal=True,
    )
    return {"action": "draw", "session": snap}


@router.post("/ready-cut")
def ready_cut(body: DismissIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.ready_cut(body.character_id)


@router.post("/cut")
def cut(body: CutIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.cut(body.character_id, body.entropy or "")


@router.post("/pick")
def pick(body: PickIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.pick(body.character_id, body.fan_index)


@router.post("/her-draw")
def her_draw(body: DismissIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.her_draw(body.character_id)


@router.post("/reveal")
def reveal(body: RevealIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.reveal(body.character_id, body.index)


@router.post("/clarifier")
def clarifier(body: ClarifierIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.clarifier(body.character_id, body.host)


@router.post("/linger")
def linger(body: DismissIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.enter_linger(body.character_id)


@router.post("/synth-done")
def synth_done(body: DismissIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.mark_synth_done(body.character_id)


@router.post("/seal")
def seal(body: DismissIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.seal_linger(body.character_id)


@router.post("/draw")
def draw(body: DrawIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    if service.active(body.character_id) and not body.redeal:
        return {"action": "keep", "session": service.snapshot(body.character_id)}
    snap = service.begin(
        body.character_id, body.spread, body.question or "", redeal=True,
    )
    return {"action": "draw", "session": snap}


@router.post("/intent")
def intent(body: IntentIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    action = service.apply_user_text(body.character_id, "user", body.text or "")
    if action == "draw":
        service.set_question(body.character_id, body.question or "")
    snap = service.snapshot(body.character_id)
    if action == "dismiss":
        snap = service._empty_session()
        snap["exited"] = True
    return {"action": action, "session": snap}


@router.post("/focus")
def focus(body: FocusIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return service.set_focus(body.character_id, body.index)


@router.post("/dismiss")
def dismiss(body: DismissIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    was = service.active(body.character_id)
    service.clear(body.character_id, exited=was)
    snap = service._empty_session()
    snap["exited"] = was
    return {"action": "dismiss" if was else "none", "session": snap}
