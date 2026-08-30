"""对话接口：SSE 流式，含情绪标签事件。"""
import json
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Asset, Character, ChatMessage
from ..conversation import HISTORY_FETCH, HISTORY_QA_MESSAGES, SIDE_KINDS
from ..modules import hooks
from ..services import duplex as duplex_service
from ..services import ingress as ingress_service
from ..services import llm as llm_service
from ..services import settings_store
from ..services.catalog import classify_motion, strip_category_prefix

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    character_id: int
    text: str
    morphs: List[str] = []
    mode: str = "user"
    scene_id: str = ""
    scene_text: str = ""
    scene_title: str = ""
    scene_conflict: str = ""
    scene_opening: str = ""
    scene_cam: str = ""
    scene_intent: str = ""
    scene_background: str = ""
    scene_avoid: str = ""
    scene_salt: str = ""
    variation: str = ""
    reroll: bool = False


class ContinueRequest(BaseModel):
    character_id: int
    morphs: List[str] = []


class IngressRequest(BaseModel):
    text: str
    busy: str = "speech"
    last_user: str = ""
    last_assistant: str = ""


def _msg_out(m: ChatMessage) -> Dict[str, Any]:
    created = ""
    if m.created_at:
        created = m.created_at.isoformat()
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "kind": m.kind or "qa",
        "created_at": created,
    }


def _prompt_history(rows: List[ChatMessage]) -> List[Dict[str, str]]:
    """欢迎/告别太多会把真聊天挤出窗口。prompt 里优先留 QA。"""
    chrono = list(reversed(rows))
    qa = [m for m in chrono if (m.kind or "qa") not in SIDE_KINDS]
    side = [m for m in chrono if (m.kind or "qa") in SIDE_KINDS]
    keep = qa[-HISTORY_QA_MESSAGES:] + side[-2:]
    keep.sort(key=lambda m: m.id or 0)
    return [{"role": m.role, "content": m.content} for m in keep]


@router.post("")
async def chat(req: ChatRequest, request: Request, session: Session = Depends(get_session)):
    conf = settings_store.get_all(session)
    char = session.get(Character, req.character_id)
    persona = char.persona if char else ""

    history_rows = session.exec(
        select(ChatMessage)
        .where(ChatMessage.character_id == req.character_id)
        .order_by(ChatMessage.id.desc()).limit(HISTORY_FETCH)
    ).all()
    history: List[Dict[str, str]] = _prompt_history(history_rows)
    mode = (req.mode or "user").lower()
    sidecar = mode in ("continue", "proactive", "goodbye", "welcome")
    if not sidecar and not req.reroll:
        history.append({"role": "user", "content": req.text})

    groups: Dict[str, List[str]] = {"idle": [], "greet": [], "interact": [], "dance": []}
    for a in session.exec(select(Asset).where(Asset.kind == "motion")).all():
        try:
            cat = json.loads(a.meta or "{}").get("category") or ""
        except json.JSONDecodeError:
            cat = ""
        if cat not in groups:
            cat = classify_motion(f"{a.label} {a.name}")
        if cat == "dance":
            label = strip_category_prefix(a.label or "") or a.name
            groups[cat].append(f"{a.name}（{label}）" if label != a.name else a.name)
        else:
            groups.setdefault(cat, []).append(a.name)
    messages = llm_service.build_messages(persona, groups, history, req.morphs)

    extra = {
        "scene_id": req.scene_id,
        "scene_text": req.scene_text,
        "scene_title": req.scene_title,
        "scene_conflict": req.scene_conflict,
        "scene_opening": req.scene_opening,
        "scene_cam": req.scene_cam,
        "scene_intent": req.scene_intent,
        "scene_background": req.scene_background,
        "scene_avoid": req.scene_avoid,
        "scene_salt": req.scene_salt,
        "variation": req.variation,
    }
    messages = hooks.before_messages(session, req.character_id, mode, messages, extra)

    user_row_id: Optional[int] = None
    if not sidecar and not req.reroll:
        user_row = ChatMessage(
            character_id=req.character_id, role="user", content=req.text, kind="qa")
        session.add(user_row)
        session.commit()
        session.refresh(user_row)
        user_row_id = user_row.id

    llm_conf = conf.get("llm") or {}
    dx = duplex_service.duplex_conf(conf)
    hint = {
        "continue": duplex_service.CONTINUE_HINT,
        "proactive": duplex_service.PROACTIVE_HINT,
        "goodbye": duplex_service.GOODBYE_HINT,
        "welcome": duplex_service.WELCOME_HINT,
    }.get(mode)
    playing = hooks.scene_playing(session, req.character_id, extra)
    if mode == "goodbye":
        reason = (req.text or "").strip().lower()
        extra_g = (
            "本次是会话总时长到了 SessionTimeover。"
            if "timeover" in reason
            else "本次是用户沉默超时 SessionTimeout。"
        )
        hint = f"{duplex_service.GOODBYE_HINT} {extra_g}"
    elif mode == "welcome" and playing:
        hint = None
    elif mode == "welcome" and (req.text or "").strip():
        hint = f"{duplex_service.WELCOME_HINT}\n补充：{(req.text or '').strip()}"
    if hint:
        messages = messages + [{"role": "system", "content": hint}]
    messages = hooks.after_messages(session, req.character_id, mode, messages, extra)
    unit_kind = {
        "continue": "delayed",
        "proactive": "proactive",
        "goodbye": "goodbye",
        "welcome": "welcome",
    }.get(mode, "body")
    msg_kind = {
        "continue": "delayed",
        "proactive": "proactive",
        "goodbye": "goodbye",
        "welcome": "welcome",
    }.get(mode, "qa")

    async def event_stream():
        full_text = ""
        dropped = False
        t0 = time.perf_counter()
        llm_ms = speech_ms = None
        source = llm_service.stream_chat(llm_conf, messages)
        annotated = duplex_service.annotate_stream(
            source,
            body_cmd=dx["body_cmd"],
            filler=dx["filler"] and not sidecar,
            delayed_sec=0 if sidecar else dx["delayed_sec"],
            unit_kind=unit_kind,
        )
        try:
            async for ev in annotated:
                if await request.is_disconnected():
                    dropped = True
                    break
                kind = ev.get("type")
                if llm_ms is None and kind == "text":
                    llm_ms = int((time.perf_counter() - t0) * 1000)
                if (
                    speech_ms is None
                    and kind == "speech"
                    and ev.get("kind") != "filler"
                ):
                    speech_ms = int((time.perf_counter() - t0) * 1000)
                if kind == "done":
                    full_text = ev.get("full_text", "")
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            print(
                f"[perf] chat llm={llm_ms}ms speech={speech_ms}ms "
                f"total={int((time.perf_counter()-t0)*1000)}ms "
                f"q={(req.text or '')[:32]!r}"
            )
            close = getattr(annotated, "aclose", None)
            if close:
                try:
                    await close()
                except Exception:
                    pass
        assistant_id = None
        if full_text and not dropped:
            from ..db import engine as db_engine
            from sqlmodel import Session as DbSession
            with DbSession(db_engine) as s2:
                row = ChatMessage(
                    character_id=req.character_id,
                    role="assistant", content=full_text, kind=msg_kind)
                s2.add(row)
                s2.commit()
                s2.refresh(row)
                assistant_id = row.id
            hooks.schedule_after_reply(
                req.character_id, mode, req.text if not sidecar else "", full_text)
        meta = {"type": "meta", "user_id": user_row_id, "message_id": assistant_id}
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/continue")
async def chat_continue(req: ContinueRequest, request: Request, session: Session = Depends(get_session)):
    """静音超时后续一句（SkipOnNew）。不写入用户假消息。"""
    wrapped = ChatRequest(character_id=req.character_id, text="（对方沉默）",
                          morphs=req.morphs, mode="continue")
    return await chat(wrapped, request, session)


@router.post("/ingress")
async def chat_ingress(req: IngressRequest, session: Session = Depends(get_session)):
    """正在跳/正在说时，用户新文本：drop 附和、hold 等说完、cut 立刻开新一轮。"""
    busy = req.busy if req.busy in ("dance", "speech", "generate") else "speech"
    conf = settings_store.get_all(session)
    if not bool((conf.get("tts") or {}).get("duplex_ingress", True)):
        return {"act": "cut"}
    act = await ingress_service.decide(
        conf.get("llm") or {},
        text=req.text,
        busy=busy,
        last_user=req.last_user,
        last_assistant=req.last_assistant,
    )
    print(f"[perf] ingress busy={busy} act={act} q={(req.text or '')[:32]!r}")
    return {"act": act}


@router.get("/history/{character_id}")
def history(character_id: int, limit: int = 50,
            session: Session = Depends(get_session)):
    rows = session.exec(
        select(ChatMessage).where(ChatMessage.character_id == character_id)
        .order_by(ChatMessage.id.desc()).limit(limit)
    ).all()
    return [_msg_out(m) for m in reversed(rows)]


@router.delete("/history/{character_id}")
def clear_history(character_id: int, session: Session = Depends(get_session)):
    for row in session.exec(
        select(ChatMessage).where(ChatMessage.character_id == character_id)
    ).all():
        session.delete(row)
    session.commit()
    return {"ok": True}
