"""回溯：裁掉某条之后的消息。"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ...db import get_session
from ...models import ChatMessage
from ..flags import enabled

router = APIRouter(prefix="/api/modules/rewrite", tags=["modules-rewrite"])


class RewindIn(BaseModel):
    character_id: int
    message_id: int
    inclusive: bool = False


class DropIn(BaseModel):
    character_id: int
    message_id: int


@router.post("/rewind")
def rewind(body: RewindIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    if not enabled(session, "rewrite"):
        raise HTTPException(404, "rewrite module off")
    rows = session.exec(
        select(ChatMessage).where(ChatMessage.character_id == body.character_id)
    ).all()
    n = 0
    for row in rows:
        if row.id is None:
            continue
        drop = row.id >= body.message_id if body.inclusive else row.id > body.message_id
        if drop:
            session.delete(row)
            n += 1
    session.commit()
    left = session.exec(
        select(ChatMessage)
        .where(ChatMessage.character_id == body.character_id)
        .order_by(ChatMessage.id.asc())
    ).all()
    return {
        "ok": True,
        "removed": n,
        "messages": [_msg(m) for m in left],
    }


@router.post("/drop")
def drop_message(body: DropIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    if not enabled(session, "rewrite"):
        raise HTTPException(404, "rewrite module off")
    row = session.get(ChatMessage, body.message_id)
    if not row or row.character_id != body.character_id:
        raise HTTPException(404, "message not found")
    session.delete(row)
    session.commit()
    return {"ok": True}


def _msg(m: ChatMessage) -> Dict[str, Any]:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "kind": m.kind or "qa",
    }
