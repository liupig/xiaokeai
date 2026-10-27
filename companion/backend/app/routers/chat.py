"""对话接口：SSE 流式，含情绪标签事件。"""
import asyncio
import json
import re
import threading
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
from ..locale_pack import normalize, prompts as locale_prompts, resolve_turn, set_reply
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
    codewatch_phase: str = ""
    codewatch_title: str = ""
    codewatch_tools: str = ""
    codewatch_project: str = ""
    codewatch_source: str = ""


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


async def _speak_first(source, lead: str):
    """点舞的铺垫先送出去，技能调用留在这一句后面。"""
    if lead:
        yield {"type": "text", "delta": lead}
    async for ev in source:
        if ev.get("type") == "done" and lead and not str(ev.get("full_text") or "").startswith(lead):
            ev = {**ev, "full_text": lead + str(ev.get("full_text") or "")}
        yield ev


def _plain(text: str) -> str:
    text = re.sub(r"\[(dance|draw|lookup|glance):[^\[\]]{0,160}\]", "", text or "")
    text = re.sub(r"\[(emo|act|cam|expr|intent|stand):[^\[\]]{1,80}\]", "", text)
    return text.strip()


def _after_reply(cid: int, mode: str, user: str, text: str, prompt: str, tokens: int) -> None:
    """记账和记忆都不占用回这条语音的线程。"""
    try:
        hooks.schedule_after_reply(cid, mode, user, text)
    except Exception:
        pass
    try:
        from ..services.coins import grant_talk
        grant_talk(prompt, text, tokens)
    except Exception:
        pass


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


def _prompt_leak(text: str) -> bool:
    """模型把导演提示念进回复后，下一轮会顺着这段自言自语继续乱。"""
    t = text or ""
    return "按照要求" in t or "先看指令" in t or "【这一轮任务】" in t


def _prompt_history(rows: List[ChatMessage]) -> List[Dict[str, str]]:
    """欢迎/告别太多会把真聊天挤出窗口。prompt 里优先留 QA。"""
    chrono = list(reversed(rows))
    chrono = [m for m in chrono if not (m.role == "assistant" and _prompt_leak(m.content))]
    qa = [m for m in chrono if (m.kind or "qa") not in SIDE_KINDS]
    side = [m for m in chrono if (m.kind or "qa") in SIDE_KINDS]
    keep = qa[-HISTORY_QA_MESSAGES:] + side[-2:]
    keep.sort(key=lambda m: m.id or 0)
    return [{"role": m.role, "content": m.content} for m in keep]


@router.post("")
async def chat(req: ChatRequest, request: Request, session: Session = Depends(get_session)):
    conf = settings_store.get_all(session)
    lang = resolve_turn(conf, req.text or "", (req.mode or "user").lower())
    loc = dict(conf.get("locale") or {})
    if (loc.get("reply_mode") or "fixed") == "follow" and normalize(loc.get("reply") or "zh-CN") != lang:
        from ..locale_pack import align_voice, voice_lang
        loc["ui"] = normalize(loc.get("ui") or "zh-CN")
        loc["reply"] = lang
        loc["reply_mode"] = "follow"
        tts_row = dict(conf.get("tts") or {})
        voiced = align_voice(str(tts_row.get("engine") or ""), str(tts_row.get("voice") or ""), lang)
        patch: Dict[str, Any] = {"locale": loc}
        if voiced and voiced != tts_row.get("voice"):
            book = dict(tts_row.get("voice_by_lang") or {})
            old_reply = normalize((conf.get("locale") or {}).get("reply") or "zh-CN")
            old_voice = str(tts_row.get("voice") or "")
            if voice_lang(str(tts_row.get("engine") or ""), old_voice) == old_reply:
                book[old_reply] = old_voice
            book[lang] = voiced
            tts_row["voice"] = voiced
            tts_row["voice_by_lang"] = book
            patch["tts"] = tts_row
        settings_store.update(session, patch)
        conf = settings_store.get_all(session)
    set_reply(lang)
    char = session.get(Character, req.character_id)
    persona = char.persona if char else ""

    history_rows = session.exec(
        select(ChatMessage)
        .where(ChatMessage.character_id == req.character_id)
        .order_by(ChatMessage.id.desc()).limit(HISTORY_FETCH)
    ).all()
    history: List[Dict[str, str]] = _prompt_history(history_rows)
    mode = (req.mode or "user").lower()
    sidecar = mode in ("continue", "proactive", "goodbye", "welcome", "codewatch", "touch", "along")
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
        "codewatch_phase": req.codewatch_phase,
        "codewatch_title": req.codewatch_title,
        "codewatch_tools": req.codewatch_tools,
        "codewatch_project": req.codewatch_project,
        "codewatch_source": req.codewatch_source,
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
    dxp = (locale_prompts().get("duplex") or {})
    hint = {
        "continue": dxp.get("continue") or duplex_service.CONTINUE_HINT,
        "proactive": dxp.get("proactive") or duplex_service.PROACTIVE_HINT,
        "goodbye": dxp.get("goodbye") or duplex_service.GOODBYE_HINT,
        "welcome": dxp.get("welcome") or duplex_service.WELCOME_HINT,
    }.get(mode)
    playing = hooks.scene_playing(session, req.character_id, extra)
    if mode == "goodbye":
        reason = (req.text or "").strip().lower()
        extra_g = (
            str(dxp.get("goodbye_timeover") or "本次是会话总时长到了 SessionTimeover。")
            if "timeover" in reason
            else str(dxp.get("goodbye_timeout") or "本次是用户沉默超时 SessionTimeout。")
        )
        hint = f"{dxp.get('goodbye') or duplex_service.GOODBYE_HINT} {extra_g}"
    elif mode == "welcome" and playing:
        hint = None
    elif playing and mode == "continue":
        hint = duplex_service.CONTINUE_IN_SCENE if lang == "zh-CN" else str(dxp.get("continue_scene") or duplex_service.CONTINUE_IN_SCENE)
    elif playing and mode == "proactive":
        hint = duplex_service.PROACTIVE_IN_SCENE if lang == "zh-CN" else str(dxp.get("proactive_scene") or duplex_service.PROACTIVE_IN_SCENE)
    elif mode == "welcome" and (req.text or "").strip():
        extra_w = str(dxp.get("welcome_extra") or "补充：")
        hint = f"{dxp.get('welcome') or duplex_service.WELCOME_HINT}\n{extra_w}{(req.text or '').strip()}"
    tarot_afterglow = False
    if module_on(session, "tarot"):
        from ..modules.tarot.service import peek_exited as tarot_peek_exited
        tarot_afterglow = tarot_peek_exited(req.character_id)
    if tarot_now and mode == "continue":
        from ..modules.tarot.service import snapshot as tarot_snap
        phase = str((tarot_snap(req.character_id) or {}).get("phase") or "")
        if phase == "synth":
            hint = str(dxp.get("tarot_synth") or duplex_service.TAROT_SYNTH_HINT)
        else:
            hint = str(dxp.get("tarot_continue") or (
                "还在看牌这场戏里。按临时身份里【这一轮任务】往下讲指定的那一张，"
                "不要问对方还看不看、要不要再抽，不要寒暄，不要说「还在扒拉牌阵吗」。"
            ))
    elif tarot_now and mode == "proactive":
        hint = None
    elif tarot_afterglow and mode in ("continue", "proactive", "user"):
        hint = str(dxp.get("afterglow") or duplex_service.AFTERGLOW_HINT)
    elif mode == "codewatch":
        from ..modules.codewatch.speak import from_request as codewatch_hint
        hint = codewatch_hint(extra)
    if hint:
        messages = messages + [{"role": "system", "content": hint}]
    messages = hooks.after_messages(session, req.character_id, mode, messages, extra)
    if mode == "touch" and module_on(session, "touch"):
        from ..modules.touch.speak import hint_for as touch_hint
        messages = messages + [{"role": "system", "content": touch_hint(req.text or "")}]
    touch_off = mode == "touch" and not module_on(session, "touch")
    unit_kind = {
        "continue": "delayed",
        "proactive": "proactive",
        "goodbye": "goodbye",
        "welcome": "welcome",
        "codewatch": "proactive",
        "touch": "proactive",
        "along": "proactive",
    }.get(mode, "body")
    body_cmd = dx["body_cmd"]
    delayed_sec = 0 if sidecar else dx["delayed_sec"]
    if mode == "codewatch" or mode == "touch" or mode == "along":
        body_cmd = "queue"
        delayed_sec = 0
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
        "codewatch": "aside",
        "touch": "aside",
        "along": "proactive",
    }.get(mode, "rp" if isolate else "qa")

    from ..modules.harness.brief import host_brief, wants_harness
    use_harness = wants_harness(
        enabled=module_on(session, "harness"),
        mode=mode,
        reroll=bool(req.reroll),
        afterglow=tarot_afterglow,
    )
    harness_brief = host_brief(messages, groups.get("dance") or []) if use_harness else ""
    harness_prior = history[:-1] if history and history[-1].get("role") == "user" else list(history)
    wish_note = ""
    if use_harness and module_on(session, "memory"):
        from .coins import latest_wish_note
        wish_note = latest_wish_note(session, req.character_id)
    glance_on = module_on(session, "glance")
    harness_on = module_on(session, "harness")
    # 流开始前放开这条连接。生成器里再碰会话，会把库锁挂到整段语音结束。
    session.commit()
    session.close()
    if use_harness:
        from ..services.coins import purse_line

        purse = await asyncio.to_thread(purse_line)
        if purse:
            wish_note = f"{wish_note}\n\n{purse}".strip() if wish_note else purse

    async def event_stream():
        full_text = ""
        linked_topic = ""
        billed_tokens = 0
        dropped = False
        t0 = time.perf_counter()
        llm_ms = speech_ms = None
        if mode == "user":
            from ..modules.glance.along import note_user
            note_user(
                req.text or "",
                req.character_id,
                glance=glance_on,
                harness=harness_on,
            )
        if tarot_ev:
            yield f"data: {json.dumps(tarot_ev, ensure_ascii=False)}\n\n"
        if tarot_silent or touch_off:
            if tarot_silent:
                print(f"[tarot] skip extra continue cid={req.character_id}")
            yield f"data: {json.dumps({'type': 'done', 'full_text': ''})}\n\n"
            meta = {"type": "meta", "user_id": user_row_id, "message_id": None}
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            return
        from ..services.coins import asks_purse, purse_say

        purse_answer = await asyncio.to_thread(purse_say) if mode == "user" and asks_purse(req.text or "") else ""

        if mode == "along":
            seen = (req.text or "").strip()
            from ..modules.glance.along import candidate_alive, finish_speak, open_candidate

            note = "" if tarot_now or not use_harness or not glance_on else open_candidate(seen, harness_prior)
            if not seen or not note:
                yield f"data: {json.dumps({'type': 'done', 'full_text': ''})}\n\n"
                yield f"data: {json.dumps({'type': 'meta', 'user_id': None, 'message_id': None})}\n\n"
                return

            async def along_turns():
                from ..modules.glance.along import live as along_live
                from ..modules.glance.along import pending_trace
                from ..modules.glance.trace import mark as mark_trace
                from ..modules.glance.situation import situation
                from ..modules.glance.watch import along_turn, hollow_company, parse_reaction

                nonlocal linked_topic
                instruction = along_turn(situation.talk)
                pieces: list[str] = []
                trace_id = pending_trace()

                def _told(action: str, spoken: str = "") -> None:
                    mark_trace(
                        trace_id,
                        xiaoke_in=instruction + "\n" + note,
                        xiaoke_raw="".join(pieces),
                        xiaoke_out=spoken,
                        xiaoke_action=action,
                    )

                along_messages = [
                    {"role": "system", "content": (harness_brief + "\n\n" + note)[:6000]},
                    {"role": "user", "content": instruction},
                ]
                async for ev in llm_service.stream_chat(llm_conf, along_messages):
                    if ev.get("type") in {"glance", "lookup"}:
                        continue
                    if ev.get("type") == "text":
                        pieces.append(str(ev.get("delta") or ""))
                    if ev.get("type") != "done":
                        if pieces and not candidate_alive():
                            finish_speak(False)
                            _told("drop")
                            yield {"type": "done", "full_text": ""}
                            return
                        continue
                    topic = along_live.candidate.topic_id if along_live.candidate is not None else ""
                    parsed = parse_reaction("".join(pieces), topic)
                    if parsed is None or parsed[0] == "silent" or not candidate_alive():
                        finish_speak(False)
                        _told("silent")
                        yield {"type": "done", "full_text": ""}
                        return
                    spoken = parsed[1]
                    if hollow_company(spoken):
                        finish_speak(False)
                        _told("hollow", spoken)
                        yield {"type": "done", "full_text": ""}
                        return
                    finish_speak(True, spoken)
                    _told("speak", spoken)
                    linked_topic = topic
                    yield {"type": "text", "delta": spoken}
                    yield {"type": "done", "full_text": spoken, "topic_id": topic}
                    return

            source = prompt_stack.guard_refusal(along_turns())
        elif purse_answer:
            async def purse_turns():
                yield {"type": "text", "delta": purse_answer}
                yield {"type": "done", "full_text": purse_answer}

            source = prompt_stack.guard_refusal(purse_turns())
        elif use_harness:
            from ..modules.harness.brief import dance_opening
            from ..modules.harness.service import stream_reply

            from ..modules.websearch.service import accept_query, lookup_note
            from ..modules.glance.service import glance_from_user, glance_note

            eyes_on = glance_on

            async def harness_turns():
                dance = "" if tarot_now else dance_opening(req.text or "", harness_prior)
                recall = wish_note
                from ..modules.glance.along import snapshot as along_snapshot
                from ..modules.glance.situation import situation as live_situation

                if along_snapshot().get("on") and live_situation.latest is not None:
                    scene_note = live_situation.blocks()
                    recall = f"{scene_note}\n\n{recall}".strip() if recall else scene_note
                lead = ""
                searched = False
                query = ""
                saw_lookup = False
                said_lookup_line = False
                saw_glance = False
                said_glance_line = False
                glance_ask = ""
                glance_task = None
                async for ev in _speak_first(stream_reply(
                    llm_conf,
                    character_id=req.character_id,
                    user_text=req.text or "",
                    brief=harness_brief,
                    prior=harness_prior,
                    recall=recall,
                ), dance):
                    if ev.get("type") == "glance" and not eyes_on:
                        continue
                    if ev.get("type") == "glance" and not dance and not saw_lookup:
                        saw_glance = True
                        if not glance_ask:
                            glance_ask = str(ev.get("value") or "")
                        if "我看看" not in lead:
                            lead = "我看看。"
                            yield {"type": "text", "delta": "我看看。"}
                        if glance_task is None and eyes_on:
                            from ..modules.glance.service import glance_bundle

                            glance_task = asyncio.create_task(
                                asyncio.to_thread(glance_bundle, None, glance_ask)
                            )
                        continue
                    if ev.get("type") == "lookup" and not dance and not searched and not saw_glance:
                        saw_lookup = True
                        query = accept_query(str(ev.get("value") or "")) or query
                        continue
                    if saw_glance and ev.get("type") in {"text", "emo", "cam", "intent", "act", "expr", "stand", "lookup", "done"}:
                        if ev.get("type") == "text" and "我看看" in str(ev.get("delta") or ""):
                            said_glance_line = True
                            if "我看看" not in lead:
                                lead = "我看看。"
                                yield {"type": "text", "delta": "我看看。"}
                        continue
                    if query and not searched and ev.get("type") in {"text", "emo", "cam", "intent", "act", "expr", "stand", "done"}:
                        continue
                    if ev.get("type") == "text" and "我去查一下" in str(ev.get("delta") or ""):
                        said_lookup_line = True
                        lead = "我去查一下。"
                    if ev.get("type") == "text" and "我看看" in str(ev.get("delta") or ""):
                        said_glance_line = True
                    if lead and ev.get("type") == "done" and not str(ev.get("full_text") or "").startswith(lead):
                        ev = {**ev, "full_text": lead + str(ev.get("full_text") or "")}
                    yield ev
                if eyes_on and not saw_glance and not dance:
                    forced = glance_from_user(req.text or "")
                    if forced:
                        saw_glance = True
                        glance_ask = forced
                        if glance_task is None:
                            from ..modules.glance.service import glance_bundle

                            glance_task = asyncio.create_task(
                                asyncio.to_thread(glance_bundle, None, glance_ask)
                            )
                if saw_glance and not dance:
                    if "我看看" not in lead:
                        yield {"type": "text", "delta": "我看看。"}
                        lead = "我看看。"
                    from ..modules.glance.service import glance_bundle
                    from ..modules.glance.trace import mark as mark_trace

                    if glance_task is None:
                        found, trace_id = await asyncio.to_thread(glance_bundle, None, glance_ask)
                    else:
                        found, trace_id = await glance_task
                    from ..modules.glance.along import seed_seen
                    from ..modules.glance.situation import situation
                    from ..modules.glance.watch import along_turn, hollow_company, screen_beat

                    seed_seen(found)
                    if "这一眼没有能接的句子" in found:
                        mark_trace(trace_id, xiaoke_in=found, xiaoke_out=lead, xiaoke_action="silent")
                        yield {"type": "done", "full_text": lead}
                        return
                    line = found.split("【眼前】")[-1].strip()
                    ask_her = along_turn(situation.talk)
                    where = {
                        "movie": "片子里的一句",
                        "music": "歌里的一句",
                        "video": "画面里的一句",
                        "code": "屏幕上的一句",
                        "game": "这一局里的一句",
                        "slides": "这一页上的一句",
                    }.get(situation.scene, "眼前的一句")
                    beat = screen_beat(line, attention=situation.attention, talk=situation.talk, where=where)
                    beat = beat + "\n" + situation.blocks()
                    react = [
                        {"role": "system", "content": (harness_brief + "\n\n" + beat)[:6000]},
                        {"role": "user", "content": ask_her},
                    ]
                    buf: list[str] = []
                    failed = False
                    async for ev in llm_service.stream_chat(llm_conf, react):
                        if ev.get("type") in {"glance", "lookup", "text"}:
                            if ev.get("type") == "text":
                                buf.append(str(ev.get("delta") or ""))
                            continue
                        if ev.get("type") == "error":
                            failed = True
                            yield ev
                            break
                        if ev.get("type") != "done":
                            continue
                    spoken = re.sub(r"\[[^\]]*\]", "", "".join(buf)).strip()
                    if failed or not spoken or spoken in {"不说", "不说。"} or hollow_company(spoken):
                        mark_trace(
                            trace_id,
                            xiaoke_in=ask_her + "\n" + beat,
                            xiaoke_raw=spoken,
                            xiaoke_out=lead,
                            xiaoke_action="hollow" if spoken else "silent",
                        )
                        yield {"type": "done", "full_text": lead}
                        return
                    full = lead + spoken
                    mark_trace(
                        trace_id,
                        xiaoke_in=ask_her + "\n" + beat,
                        xiaoke_raw=spoken,
                        xiaoke_out=full,
                        xiaoke_action="speak",
                    )
                    yield {"type": "text", "delta": spoken}
                    yield {"type": "done", "full_text": full}
                    return
                if not query and saw_lookup and not dance:
                    async for ev in stream_reply(
                        llm_conf,
                        character_id=req.character_id,
                        user_text="刚才的检索词不能查。按上一句的事自己改写成一个短词，只写 [lookup:检索词]，不要说话。",
                        brief="",
                        prior=harness_prior,
                        recall=wish_note,
                    ):
                        if ev.get("type") == "lookup":
                            query = accept_query(str(ev.get("value") or "")) or query
                            continue
                        if ev.get("type") == "error":
                            yield ev
                            yield {"type": "done", "full_text": lead}
                            return
                if searched or not query:
                    return
                if said_lookup_line:
                    lead = "我去查一下。"
                elif "我去查一下" not in lead:
                    yield {"type": "text", "delta": "我去查一下。"}
                    lead = "我去查一下。" + lead
                found = await asyncio.to_thread(lookup_note, query)
                recall = f"{wish_note}\n\n{found}".strip() if wish_note else found
                finished = False
                async for ev in stream_reply(
                    llm_conf,
                    character_id=req.character_id,
                    user_text="页面到了。按【现场】把刚才要查的事实说完。搜索页上的数字优先。不要重复铺垫，不要再写标记。",
                    brief="",
                    prior=None,
                    recall=recall,
                ):
                    if ev.get("type") == "lookup":
                        continue
                    if ev.get("type") == "error":
                        yield ev
                        yield {"type": "done", "full_text": lead}
                        return
                    if ev.get("type") == "done":
                        finished = True
                        ev = {**ev, "full_text": lead + str(ev.get("full_text") or "")}
                    yield ev
                if not finished:
                    yield {"type": "done", "full_text": lead}

            source = prompt_stack.guard_refusal(harness_turns())
        else:
            source = prompt_stack.guard_refusal(llm_service.stream_chat(llm_conf, messages))
        from ..modules.draw.service import realize_draws
        annotated = realize_draws(
            duplex_service.annotate_stream(
                source,
                body_cmd=body_cmd,
                filler=dx["filler"] and not sidecar and not tarot_now,
                delayed_sec=delayed_sec,
                unit_kind=unit_kind,
            ),
            llm_conf,
            character_id=req.character_id,
            allow=not tarot_now,
            user_text=req.text or "",
            prior=harness_prior,
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
                if kind == "usage":
                    try:
                        billed_tokens = max(billed_tokens, int(ev.get("total_tokens") or 0))
                    except (TypeError, ValueError):
                        pass
                if kind == "done":
                    full_text = ev.get("full_text", "")
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            from ..modules.glance.along import release_user_turn
            release_user_turn()
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
            saved_text = full_text
            saved_kind = msg_kind
            saved_cid = req.character_id
            saved_mode = mode
            saved_user = req.text if not sidecar else ""
            saved_prompt = "\n".join(str(item.get("content") or "") for item in messages)
            saved_tokens = billed_tokens

            def _persist() -> Optional[int]:
                # 落库会等 SQLite。放在事件循环里时，已经发出的这句话进不了语音进程。
                from ..db import engine as db_engine
                from sqlmodel import Session as DbSession
                row_id = None
                with DbSession(db_engine) as s2:
                    row = ChatMessage(
                        character_id=saved_cid,
                        role="assistant", content=saved_text,
                        full_content=saved_text, kind=saved_kind)
                    s2.add(row)
                    s2.commit()
                    s2.refresh(row)
                    row_id = row.id
                talk_log.write("full", _plain(saved_text),
                               character_id=saved_cid, msg_kind=saved_kind)
                # 记账和记忆会占住线程好几秒。语音还在等这个线程池，就不能先出声。
                threading.Thread(
                    target=_after_reply,
                    args=(saved_cid, saved_mode, saved_user, saved_text, saved_prompt, saved_tokens),
                    daemon=True,
                    name="after-reply",
                ).start()
                return row_id

            assistant_id = await asyncio.to_thread(_persist)
        meta = {"type": "meta", "user_id": user_row_id, "message_id": assistant_id}
        if linked_topic:
            meta["topic_id"] = linked_topic
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
    session.commit()
    session.close()
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
