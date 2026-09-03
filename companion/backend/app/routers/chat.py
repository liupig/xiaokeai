"""对话接口：SSE 流式，含情绪标签事件。"""
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Asset, Character, ChatMessage
from ..conversation import HISTORY_FETCH, HISTORY_QA_MESSAGES, SIDE_KINDS
from ..modules import hooks
from ..modules.flags import enabled as module_on
from ..services import duplex as duplex_service
from ..services import ingress as ingress_service
from ..services import llm as llm_service
from ..services import prompt_stack
from ..services import settings_store
from ..services.catalog import classify_motion, strip_category_prefix
from .. import talk_log

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
    scene_resume: str = ""
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


def _when_local(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _plain(text: str) -> str:
    return re.sub(r"\[(emo|act|dance|cam|expr|intent|stand):[^\[\]]{1,80}\]", "", text or "").strip()


def _msg_out(m: ChatMessage) -> Dict[str, Any]:
    created = ""
    if m.created_at:
        created = m.created_at.isoformat()
    full = (m.full_content or "").strip() or (m.content or "")
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "full_content": full,
        "kind": m.kind or "qa",
        "created_at": created,
        "when": _when_local(m.created_at),
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
    # 固定架子每轮重拼：persona -> 上下文槽+场景包 -> 扮演 overlay -> 导演手册。
    # history_rows 按 id 倒序，第 0 条是上一条消息，用来算「距上次聊天」。
    last_at = history_rows[0].created_at if history_rows else None
    messages = prompt_stack.build_messages(
        persona=persona,
        char_name=(char.name if char else ""),
        motion_groups=groups,
        history=history,
        user_text=req.text or "",
        mode=mode,
        last_at=last_at,
        character_id=req.character_id,
        boundary=(getattr(char, "boundary", "") or "strict") if char else "strict",
    )
    # 扮演期间的消息落库标记为 rp：留在聊天历史里，但不进长期记忆抽取
    rp_now = prompt_stack.overlay_active(req.character_id)

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
        "scene_resume": req.scene_resume,
        "variation": req.variation,
        "user_text": req.text or "",
    }
    messages = hooks.before_messages(session, req.character_id, mode, messages, extra)

    tarot_now = False
    tarot_silent = False
    tarot_ev = None
    if module_on(session, "tarot"):
        from ..modules.tarot.service import active as tarot_active
        from ..modules.tarot.service import should_speak as tarot_should_speak
        from ..modules.tarot.service import progress_event as tarot_progress
        tarot_now = tarot_active(req.character_id)
        if tarot_now and mode == "continue":
            tarot_silent = not tarot_should_speak(req.character_id)
        tarot_ev = tarot_progress(req.character_id, consume_exit=True)
    isolate = rp_now or tarot_now

    user_row_id: Optional[int] = None
    if not sidecar and not req.reroll:
        user_row = ChatMessage(
            character_id=req.character_id, role="user", content=req.text,
            kind="rp" if isolate else "qa")
        session.add(user_row)
        session.commit()
        session.refresh(user_row)
        user_row_id = user_row.id
        talk_log.write("user", req.text, character_id=req.character_id)

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
    elif playing and mode == "continue":
        hint = duplex_service.CONTINUE_IN_SCENE
    elif playing and mode == "proactive":
        hint = duplex_service.PROACTIVE_IN_SCENE
    elif mode == "welcome" and (req.text or "").strip():
        hint = f"{duplex_service.WELCOME_HINT}\n补充：{(req.text or '').strip()}"
    if tarot_now and mode == "continue":
        hint = (
            "还在看牌这场戏里。按临时身份里【这一轮任务】往下讲指定的那一张，"
            "不要问对方还看不看、要不要再抽，不要寒暄，不要说「还在扒拉牌阵吗」。"
        )
    elif tarot_now and mode == "proactive":
        hint = None
    if hint:
        messages = messages + [{"role": "system", "content": hint}]
    messages = hooks.after_messages(session, req.character_id, mode, messages, extra)
    unit_kind = {
        "continue": "delayed",
        "proactive": "proactive",
        "goodbye": "goodbye",
        "welcome": "welcome",
    }.get(mode, "body")
    body_cmd = dx["body_cmd"]
    delayed_sec = 0 if sidecar else dx["delayed_sec"]
    if tarot_now and mode in ("user", "continue"):
        # 游戏模式：句子排队顺播。综合收线由前端在全翻后点一次 continue，不要按张自动续。
        body_cmd = "queue"
        unit_kind = "body"
        delayed_sec = 0
    msg_kind = {
        "continue": "delayed",
        "proactive": "proactive",
        "goodbye": "goodbye",
        "welcome": "welcome",
    }.get(mode, "rp" if isolate else "qa")

    async def event_stream():
        full_text = ""
        dropped = False
        t0 = time.perf_counter()
        llm_ms = speech_ms = None
        if tarot_ev:
            yield f"data: {json.dumps(tarot_ev, ensure_ascii=False)}\n\n"
        if tarot_silent:
            print(f"[tarot] skip extra continue cid={req.character_id}")
            yield f"data: {json.dumps({'type': 'done', 'full_text': ''})}\n\n"
            meta = {"type": "meta", "user_id": user_row_id, "message_id": None}
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            return
        source = prompt_stack.guard_refusal(llm_service.stream_chat(llm_conf, messages))
        annotated = duplex_service.annotate_stream(
            source,
            body_cmd=body_cmd,
            filler=dx["filler"] and not sidecar and not tarot_now,
            delayed_sec=delayed_sec,
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
            talk_log.write(
                "chat",
                f"模型 {llm_ms if llm_ms is not None else '-'}ms · "
                f"开口 {speech_ms if speech_ms is not None else '-'}ms · "
                f"整轮 {int((time.perf_counter()-t0)*1000)}ms",
                character_id=req.character_id,
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
                    role="assistant", content=full_text,
                    full_content=full_text, kind=msg_kind)
                s2.add(row)
                s2.commit()
                s2.refresh(row)
                assistant_id = row.id
            talk_log.write("full", _plain(full_text),
                           character_id=req.character_id, msg_kind=msg_kind)
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


class SpokenIn(BaseModel):
    content: str = ""


@router.patch("/message/{message_id}")
def patch_spoken(message_id: int, body: SpokenIn, session: Session = Depends(get_session)):
    """插话后把未读完的尾巴从历史里裁掉。空内容则删掉这条。"""
    row = session.get(ChatMessage, message_id)
    if not row:
        raise HTTPException(404, "message not found")
    text = (body.content or "").strip()
    if not text:
        full = _plain(row.full_content or row.content or "")
        if full:
            talk_log.write("unsaid", full, character_id=row.character_id)
        session.delete(row)
        session.commit()
        return {"ok": True, "deleted": True}
    spoken = _plain(body.content)
    full = _plain(row.full_content or row.content or "")
    row.content = body.content
    if not (row.full_content or "").strip():
        row.full_content = row.content
    session.add(row)
    session.commit()
    session.refresh(row)
    talk_log.write("spoken", spoken, character_id=row.character_id)
    if full and spoken and full != spoken:
        rest = full
        if spoken and spoken in full:
            rest = full[full.find(spoken) + len(spoken):].strip()
        if rest and rest != spoken:
            talk_log.write("unsaid", rest, character_id=row.character_id)
    return _msg_out(row)


@router.get("/talk-log")
def talk_log_today(limit: int = 400):
    """今天的后台流水账（本地时间）。"""
    cap = max(20, min(int(limit or 400), 2000))
    return {"when": talk_log.stamp(), "lines": talk_log.read_today(cap)}


@router.delete("/history/{character_id}")
def clear_history(character_id: int, session: Session = Depends(get_session)):
    for row in session.exec(
        select(ChatMessage).where(ChatMessage.character_id == character_id)
    ).all():
        session.delete(row)
    session.commit()
    return {"ok": True}
