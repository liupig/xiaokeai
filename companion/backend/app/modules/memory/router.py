"""记忆 CRUD。模块关闭时返回空列表 / 404。底层是 Mem0。"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...db import get_session
from ..flags import enabled
from . import worker as memory_worker

router = APIRouter(prefix="/api/modules/memory", tags=["modules-memory"])


def _guard(session: Session) -> None:
    if not enabled(session, "memory"):
        raise HTTPException(404, "memory module off")


class FactIn(BaseModel):
    character_id: int
    id: Optional[str] = None
    kind: str = "event"
    content: str = ""
    importance: float = 0.5
    pinned: Optional[bool] = None


@router.get("/facts/{character_id}")
def get_facts(character_id: int, session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    if not enabled(session, "memory"):
        return []
    try:
        return memory_worker.list_facts(character_id)
    except Exception as exc:
        print(f"[memory] get_facts failed: {exc}")
        return []


@router.put("/facts")
def put_fact(body: FactIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    if not body.content.strip() and not body.id:
        raise HTTPException(400, "content required")
    try:
        return memory_worker.upsert_fact(
            body.character_id,
            fact_id=body.id, kind=body.kind, content=body.content,
            importance=body.importance, pinned=body.pinned,
        )
    except KeyError:
        raise HTTPException(404, "fact not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        print(f"[memory] put_fact failed: {exc}")
        raise HTTPException(503, "记忆暂不可用") from exc


@router.delete("/facts/{character_id}/{fact_id}")
def drop_fact(character_id: int, fact_id: str,
              session: Session = Depends(get_session)) -> Dict[str, bool]:
    _guard(session)
    ok = memory_worker.delete_fact(character_id, fact_id)
    if not ok:
        raise HTTPException(404, "fact not found")
    return {"ok": True}


class PinIn(BaseModel):
    character_id: int
    message_id: int


@router.get("/pins/{character_id}")
def get_pins(character_id: int, session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    if not enabled(session, "memory"):
        return []
    try:
        return memory_worker.list_pins(character_id)
    except Exception as exc:
        print(f"[memory] get_pins failed: {exc}")
        return []


@router.put("/pins")
def put_pin(body: PinIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    try:
        return memory_worker.pin_message(body.character_id, body.message_id)
    except KeyError:
        raise HTTPException(404, "message not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        print(f"[memory] put_pin failed: {exc}")
        raise HTTPException(503, "记忆暂不可用") from exc


@router.delete("/pins/{character_id}/{pin_id}")
def drop_pin(character_id: int, pin_id: str,
             session: Session = Depends(get_session)) -> Dict[str, bool]:
    _guard(session)
    ok = memory_worker.delete_pin(character_id, pin_id)
    if not ok:
        raise HTTPException(404, "pin not found")
    return {"ok": True}


@router.get("/episodes/{character_id}")
def get_episodes(character_id: int, session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    if not enabled(session, "memory"):
        return []
    try:
        return memory_worker.list_episodes(character_id)
    except Exception as exc:
        print(f"[memory] get_episodes failed: {exc}")
        return []


@router.delete("/episodes/{character_id}/{episode_id}")
def drop_episode(character_id: int, episode_id: str,
                 session: Session = Depends(get_session)) -> Dict[str, bool]:
    _guard(session)
    ok = memory_worker.delete_episode(character_id, episode_id)
    if not ok:
        raise HTTPException(404, "episode not found")
    return {"ok": True}
