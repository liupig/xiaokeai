"""按历史窗口切 Mem0 抽取：满 9 轮新对话才抽，重叠 2 轮，游标只前进。"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from ...conversation import EXTRACT_NEW_TURNS, EXTRACT_OVERLAP_TURNS, SIDE_KINDS
from ...models import ChatMessage, MemoryExtractCursor
from ...services import settings_store
from .service import llm_extract_facts, store_extracted_facts, strip_perf


def _qa_rows(session: Session, character_id: int) -> List[ChatMessage]:
    rows = session.exec(
        select(ChatMessage)
        .where(ChatMessage.character_id == character_id)
        .order_by(ChatMessage.id)
    ).all()
    return [m for m in rows if (m.kind or "qa") not in SIDE_KINDS]


def _cursor_id(session: Session, character_id: int) -> int:
    row = session.get(MemoryExtractCursor, character_id)
    return int(row.upto_id) if row else 0


def _save_cursor(session: Session, character_id: int, upto_id: int) -> None:
    now = datetime.utcnow()
    row = session.get(MemoryExtractCursor, character_id)
    if row is None:
        session.add(MemoryExtractCursor(
            character_id=character_id, upto_id=int(upto_id), updated_at=now))
    else:
        row.upto_id = int(upto_id)
        row.updated_at = now
    session.commit()


def pick_extract_window(
    session: Session, character_id: int,
) -> Optional[Tuple[List[Dict[str, str]], int, int]]:
    """返回 (messages, 新轮数, 游标应写到的 message id)。不够一轮窗口则 None。"""
    qa = _qa_rows(session, character_id)
    if not qa:
        return None
    cursor = _cursor_id(session, character_id)
    users = [m for m in qa if m.role == "user" and (m.content or "").strip()]
    new_users = [m for m in users if int(m.id or 0) > cursor]
    if len(new_users) < EXTRACT_NEW_TURNS:
        return None

    chunk = new_users[:EXTRACT_NEW_TURNS]
    first_new = int(chunk[0].id or 0)
    last_new = int(chunk[-1].id or 0)
    next_user = next((int(u.id or 0) for u in users if int(u.id or 0) > last_new), None)
    end_id = (next_user - 1) if next_user else int(qa[-1].id or last_new)

    older = [m for m in users if int(m.id or 0) < first_new]
    overlap = older[-EXTRACT_OVERLAP_TURNS:] if EXTRACT_OVERLAP_TURNS else []
    start_id = int(overlap[0].id or first_new) if overlap else first_new

    payload: List[Dict[str, str]] = []
    for m in qa:
        mid = int(m.id or 0)
        if mid < start_id or mid > end_id:
            continue
        text = (m.content or "").strip()
        if m.role == "assistant":
            text = strip_perf(text)
        if not text:
            continue
        payload.append({"role": m.role or "user", "content": text[:1500]})
    if not any(x.get("role") == "user" for x in payload):
        return None
    return payload, len(chunk), end_id


def run_extract_job(character_id: int) -> None:
    from ...db import engine

    with Session(engine) as session:
        for _ in range(4):
            picked = pick_extract_window(session, character_id)
            if not picked:
                return
            payload, turns, end_id = picked
            print(
                f"[memory] extract window cid={character_id} new_turns={turns} "
                f"msgs={len(payload)} upto={end_id}"
            )
            conf = settings_store.get_all(session).get("llm") or {}
            facts = llm_extract_facts(conf, payload)
            if facts:
                n = store_extracted_facts(session, character_id, facts)
                print(f"[memory] extract stored={n} facts={len(facts)}")
            else:
                print("[memory] extract empty, cursor still advances")
            _save_cursor(session, character_id, end_id)
