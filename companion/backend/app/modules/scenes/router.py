from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session

from ...db import get_session
from ..flags import enabled
from .catalog import list_cards
from .service import current_for, generate_tonight, save_current

router = APIRouter(prefix="/api/modules/scenes", tags=["modules-scenes"])


class TonightIn(BaseModel):
    character_id: int = 0


class CurrentIn(BaseModel):
    character_id: int = 0
    id: str = ""
    title: str = ""
    setting: str = ""
    conflict: str = ""
    opening: str = ""
    cam: str = ""
    intent: str = ""
    background: str = ""
    assigned_day: str = ""


@router.get("/cards")
def cards(session: Session = Depends(get_session)) -> List[Dict[str, str]]:
    if not enabled(session, "scenes"):
        return []
    return list_cards()


@router.get("/current/{character_id}")
def current(
    character_id: int,
    last_user_at: int = Query(0),
    seed_id: str = Query(""),
    seed_background: str = Query(""),
    seed_day: str = Query(""),
    fresh: bool = Query(False),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    if not enabled(session, "scenes"):
        raise HTTPException(404, "scenes module off")
    return current_for(
        session, character_id,
        last_user_at=last_user_at,
        seed_id=seed_id,
        seed_background=seed_background,
        seed_day=seed_day,
        fresh=fresh,
    )


@router.put("/current")
def put_current(body: CurrentIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    if not enabled(session, "scenes"):
        raise HTTPException(404, "scenes module off")
    if not body.character_id:
        raise HTTPException(400, "character_id required")
    card = {
        "id": body.id,
        "title": body.title,
        "setting": body.setting,
        "conflict": body.conflict,
        "opening": body.opening,
        "cam": body.cam or "half",
        "intent": body.intent or "look",
        "background": body.background,
    }
    row = save_current(session, body.character_id, card, body.assigned_day or None)
    return {"card": card, "rotated": False, "assigned_day": row.assigned_day}


@router.post("/tonight")
async def tonight(body: TonightIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    if not enabled(session, "scenes"):
        raise HTTPException(404, "scenes module off")
    return await generate_tonight(session, body.character_id)
