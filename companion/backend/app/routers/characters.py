"""角色卡 CRUD。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Character

router = APIRouter(prefix="/api/characters", tags=["characters"])


@router.get("")
def list_characters(session: Session = Depends(get_session)) -> List[Character]:
    return session.exec(select(Character).order_by(Character.id)).all()


@router.post("")
def create_character(char: Character, session: Session = Depends(get_session)) -> Character:
    char.id = None
    session.add(char)
    session.commit()
    session.refresh(char)
    return char


@router.put("/{char_id}")
def update_character(char_id: int, patch: Character,
                     session: Session = Depends(get_session)) -> Character:
    char = session.get(Character, char_id)
    if not char:
        raise HTTPException(404, "角色不存在")
    for field in ("name", "model_asset_id", "persona", "boundary", "greeting",
                  "voice", "emotion_map", "idle_motion"):
        setattr(char, field, getattr(patch, field))
    session.add(char)
    session.commit()
    session.refresh(char)
    return char


@router.delete("/{char_id}")
def delete_character(char_id: int, session: Session = Depends(get_session)):
    char = session.get(Character, char_id)
    if not char:
        raise HTTPException(404, "角色不存在")
    session.delete(char)
    session.commit()
    return {"ok": True}
