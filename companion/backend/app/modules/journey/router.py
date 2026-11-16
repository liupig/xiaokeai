"""HTTP boundary for the independent shared-time module."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...db import get_session
from ..flags import enabled
from . import service


router = APIRouter(prefix='/api/modules/journey', tags=['modules-journey'])


class Configure(BaseModel):
    character_id: int
    mode: str


class Summary(BaseModel):
    character_id: int
    summary: str = ''


class Thread(BaseModel):
    character_id: int
    text: str
    due_days: int = 7


class Event(BaseModel):
    character_id: int
    kind: str
    source_id: str


class Path(BaseModel):
    character_id: int
    path: str


class Preferences(BaseModel):
    character_id: int
    preferences: list[str]


def guard(session, fn):
    if not enabled(session, 'journey'):
        raise HTTPException(404, 'module_disabled')
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get('/{character_id}')
async def get_state(character_id: int, session: Session = Depends(get_session)):
    if enabled(session, 'journey'):
        if isinstance(session, Session):
            service.backfill_chat_history(character_id, session)
        from .autonomy import schedule_if_needed
        schedule_if_needed(session, character_id)
    return guard(session, lambda: service.state(character_id))


@router.put('/mode')
def set_mode(body: Configure, session: Session = Depends(get_session)):
    return guard(session, lambda: service.configure(body.character_id, body.mode))


@router.put('/summary')
def set_summary(body: Summary, session: Session = Depends(get_session)):
    return guard(session, lambda: service.set_summary(body.character_id, body.summary))


@router.put('/path')
def set_path(body: Path, session: Session = Depends(get_session)):
    return guard(session, lambda: service.set_path(body.character_id, body.path))


@router.put('/preferences')
def set_preferences(body: Preferences, session: Session = Depends(get_session)):
    raise HTTPException(403, 'preferences_are_character_owned')


@router.post('/threads')
def create_thread(body: Thread, session: Session = Depends(get_session)):
    return guard(session, lambda: service.create_thread(body.character_id, body.text, due_days=body.due_days))


@router.put('/threads/{thread_id}/done')
def resolve_thread(thread_id: str, character_id: int, session: Session = Depends(get_session)):
    return guard(session, lambda: service.resolve_thread(character_id, thread_id))


@router.delete('/threads/{thread_id}')
def delete_thread(thread_id: str, character_id: int, session: Session = Depends(get_session)):
    return guard(session, lambda: service.delete_thread(character_id, thread_id))


@router.post('/events')
def record_event(body: Event, session: Session = Depends(get_session)):
    # Chat and memories enter through their owning services, not forgeable UI events.
    if body.kind not in {'activity', 'touch'}:
        raise HTTPException(400, 'bad_event')
    return guard(session, lambda: service.record_event(body.character_id, body.kind, body.source_id))


@router.delete('/{character_id}')
def reset(character_id: int, session: Session = Depends(get_session)):
    return guard(session, lambda: service.reset(character_id))
