"""情境注入 welcome，以及 tonight 生成。当前这场由后端按角色记住。"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import random
import re
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from ...models import Character, ChatMessage, SceneState, utc_now
from ...services import llm as llm_service
from ...services import settings_store
from .catalog import find_by_background, get_card, list_cards

AUTO_SWITCH_QUIET_MS = 3 * 60 * 60 * 1000
DAY_ROLL_HOUR = 6

# 开场：人已经在戏里，不是客服打招呼
SCENE_OPEN = (
    "对方刚走进来。你人已经站在这场戏里，现在开口。"
    "这场就是现在的现实，不是角色扮演提示，不要说『我们来演』。"
    "对方是走进这场里的人，不是来使用聊天功能的用户。"
    "不要念稿、不要自我介绍、不要『欢迎回来』、不要『想聊天还是想看跳舞』。"
    "一两句口语，必须是此刻新想的；同一场合每次换说法。"
    "禁止复述下面禁止的句子。禁止旁白描写。禁止 [dance:]。\n"
    "这场戏：{title}\n"
    "场合：{setting}\n"
    "心里那点事（还没说开）：{conflict}\n"
    "开口感觉（不是台词）：{opening}\n"
    "禁止原样说出：{avoid}\n"
    "必须带：[emo:] [cam:{cam}] [intent:{intent}]\n"
    "变化种子：{salt}，按这个感觉换一种开口。"
)

# 后续每一轮：戏没散，接着演
SCENE_STAY = (
    "你们还在这场戏里，没有散场、没有切回空白闲聊。"
    "场合没变。心里那点事还在——除非对方刚才已经把这事说开、改口，或明确要换地方、回家、不想演了。"
    "接着刚才的话往下演：不要重新介绍场合，不要再打一遍招呼，不要跳出来说这是情境卡。"
    "说话要像站在这个地方的人，细节可以随口带，不要导游腔，不要旁白。"
    "记忆里的事可以顺嘴带一句，人还站在这个场合，不要把对话拽回空白工作室或邀舞。"
    "覆盖上面默认的半身闲聊镜头：这场优先 [cam:{cam}] [intent:{intent}]，除非对方把场面拉开或拉近。"
    "不要自己开舞、不要邀舞。对方这轮如果明确要跳，必须 [dance:文件名]，可以一边跳一边还在这场里说话。"
    "对方如果明显要离开这场，用口语带走，不要宣布『场景结束』。\n"
    "这场戏：{title}\n"
    "场合：{setting}\n"
    "心里那点事：{conflict}"
)

# 同一场里再进门：接着演，不是重新开场
SCENE_RESUME = (
    "对方又走进来。你们还在这场戏里，刚才的话还在。"
    "顺着上次的情绪和没说完的事接着演，不要重新介绍场合，不要『欢迎回来』，不要当没发生过。"
    "一两句口语，必须是此刻新想的。禁止旁白，禁止 [dance:]。\n"
    "这场戏：{title}\n"
    "场合：{setting}\n"
    "心里那点事：{conflict}\n"
    "必须带：[emo:] [cam:{cam}] [intent:{intent}]"
)

SCENE_SIDECAR = (
    "还在这场戏里。对方这轮没说话。从这场的空气里再接一句，"
    "不要换到空白闲聊，不要再打招呼，不要自我介绍。"
    "一两句口语，最后轻轻追问。优先 [cam:{cam}] [intent:{intent}]。"
    "禁止 [dance:]，禁止旁白。\n"
    "这场戏：{title}\n"
    "场合：{setting}\n"
    "心里那点事：{conflict}"
)

SCENE_BYE = (
    "还在这场的门口道别，不要突然变成工作室客服。"
    "一句很短的口语，像人站在这个地方说再见。不提问，不邀舞，不旁白。\n"
    "这场戏：{title}\n"
    "场合：{setting}"
)

SCENE_DANCE = (
    "对方这轮明确要你跳舞，不是闲聊。"
    "必须输出 [dance:文件名]，从可用舞蹈列表里选一支；不要只口头答应，不要用 [intent:] 或 [act:] 代替。"
    "可以一边跳一边还站在这场场合里说话，不要切回空白工作室或邀舞客服。"
    "禁止说『我们来演』。\n"
    "这场戏：{title}\n"
    "场合：{setting}\n"
    "心里那点事：{conflict}"
)

_DANCE_ASK = re.compile(r"跳.{0,6}舞|来一段|来一支|再跳|换一支|跳一个|dance", re.I)


def scene_playing(
    session: Session,
    character_id: int,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    return resolve_scene(session, character_id, extra or {}) is not None


def inject_scene(
    session: Session,
    character_id: int,
    messages: List[Dict[str, str]],
    extra: Dict[str, Any],
    mode: str = "welcome",
) -> List[Dict[str, str]]:
    card = resolve_scene(session, character_id, extra)
    if not card:
        return messages
    phase = (mode or "user").lower()
    title = card.get("title") or "今晚"
    setting = card.get("setting") or ""
    conflict = card.get("conflict") or ""
    cam = card.get("cam") or "half"
    intent = card.get("intent") or "look"
    if phase == "welcome":
        has_talk = any(m.get("role") in ("user", "assistant") for m in messages)
        resume = _truthy(extra.get("scene_resume")) and has_talk
        keep_history = resume or (card.get("id") or "") == "unfinished"
        if resume:
            hint = SCENE_RESUME.format(
                title=title, setting=setting, conflict=conflict, cam=cam, intent=intent,
            )
        else:
            hint = SCENE_OPEN.format(
                title=title,
                setting=setting,
                conflict=conflict,
                opening=card.get("opening") or "像已经在这儿等过，随口接。",
                avoid=(extra.get("scene_avoid") or "（无固定台词）"),
                salt=(extra.get("scene_salt") or "a"),
                cam=cam,
                intent=intent,
            )
        out = list(messages) if keep_history else [m for m in messages if m.get("role") == "system"]
        out.append({"role": "system", "content": hint})
        return out
    if phase in ("continue", "proactive"):
        tmpl, kwargs = SCENE_SIDECAR, dict(title=title, setting=setting, conflict=conflict, cam=cam, intent=intent)
    elif phase == "goodbye":
        tmpl, kwargs = SCENE_BYE, dict(title=title, setting=setting)
    else:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content") or ""
                break
        if _DANCE_ASK.search(last_user):
            tmpl, kwargs = SCENE_DANCE, dict(title=title, setting=setting, conflict=conflict)
        else:
            tmpl, kwargs = SCENE_STAY, dict(title=title, setting=setting, conflict=conflict, cam=cam, intent=intent)
    out = list(messages)
    out.append({"role": "system", "content": tmpl.format(**kwargs)})
    return out


def resolve_scene(
    session: Session,
    character_id: int,
    extra: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    sid = (extra.get("scene_id") or "").strip()
    title = (extra.get("scene_title") or "").strip()
    setting = (extra.get("scene_text") or extra.get("scene_setting") or "").strip()
    if sid:
        card = get_card(sid)
        if card:
            merged = dict(card)
            if title:
                merged["title"] = title
            if setting:
                merged["setting"] = setting
            if extra.get("scene_conflict"):
                merged["conflict"] = extra["scene_conflict"]
            if extra.get("scene_opening"):
                merged["opening"] = extra["scene_opening"]
            if extra.get("scene_cam"):
                merged["cam"] = extra["scene_cam"]
            if extra.get("scene_intent"):
                merged["intent"] = extra["scene_intent"]
            if extra.get("scene_background"):
                merged["background"] = extra["scene_background"]
            return merged
    if setting or title:
        return {
            "id": sid or "tonight",
            "title": title or "今晚",
            "setting": setting,
            "conflict": extra.get("scene_conflict") or "",
            "opening": extra.get("scene_opening") or "按这场设定开口。",
            "cam": extra.get("scene_cam") or "half",
            "intent": extra.get("scene_intent") or "look",
            "background": extra.get("scene_background") or "",
        }
    stored = card_from_row(session.get(SceneState, character_id))
    return stored


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _pad2(n: int) -> str:
    return f"{n:02d}"


def scene_day(now: Optional[datetime] = None) -> str:
    d = now or datetime.now()
    if d.hour < DAY_ROLL_HOUR:
        d = d - timedelta(days=1)
    return f"{d.year}-{_pad2(d.month)}-{_pad2(d.day)}"


def next_day_roll_ms(now: Optional[datetime] = None) -> int:
    d = now or datetime.now()
    roll = d.replace(hour=DAY_ROLL_HOUR, minute=0, second=0, microsecond=0)
    if d >= roll:
        roll = roll + timedelta(days=1)
    return int(roll.timestamp() * 1000)


def card_from_row(row: Optional[SceneState]) -> Optional[Dict[str, str]]:
    if not row:
        return None
    blob: Dict[str, Any] = {}
    try:
        raw = json.loads(row.card_json or "{}")
        if isinstance(raw, dict):
            blob = raw
    except json.JSONDecodeError:
        blob = {}
    sid = str(blob.get("id") or row.scene_id or "").strip()
    builtin = get_card(sid) if sid else None
    if builtin:
        merged = dict(builtin)
        for key, val in blob.items():
            if val:
                merged[key] = str(val)
        return merged
    if blob.get("id") or blob.get("title") or blob.get("setting"):
        return {
            "id": str(blob.get("id") or sid or "tonight"),
            "title": str(blob.get("title") or "今晚"),
            "setting": str(blob.get("setting") or ""),
            "conflict": str(blob.get("conflict") or ""),
            "opening": str(blob.get("opening") or ""),
            "cam": str(blob.get("cam") or "half"),
            "intent": str(blob.get("intent") or "look"),
            "background": str(blob.get("background") or ""),
        }
    return dict(get_card(row.scene_id)) if row.scene_id and get_card(row.scene_id) else None


def save_current(session: Session, character_id: int, card: Dict[str, Any],
                 assigned_day: Optional[str] = None) -> SceneState:
    day = assigned_day or scene_day()
    payload = {
        "id": card.get("id") or "",
        "title": card.get("title") or "",
        "setting": card.get("setting") or "",
        "conflict": card.get("conflict") or "",
        "opening": card.get("opening") or "",
        "cam": card.get("cam") or "half",
        "intent": card.get("intent") or "look",
        "background": card.get("background") or "",
    }
    row = session.get(SceneState, character_id)
    if row is None:
        row = SceneState(character_id=character_id)
        session.add(row)
    row.scene_id = str(payload["id"])
    row.assigned_day = day
    row.card_json = json.dumps(payload, ensure_ascii=False)
    row.updated_at = utc_now()
    session.commit()
    session.refresh(row)
    return row


def _last_user_ms(session: Session, character_id: int, hint_ms: int = 0) -> int:
    if hint_ms > 0:
        return hint_ms
    row = session.exec(
        select(ChatMessage)
        .where(ChatMessage.character_id == character_id)
        .where(ChatMessage.role == "user")
        .order_by(ChatMessage.created_at.desc())
    ).first()
    if not row or not row.created_at:
        return 0
    return int(row.created_at.timestamp() * 1000)


def _next_rotate_ms(assigned_day: str, last_user_ms: int) -> int:
    quiet_from = (last_user_ms or 0) + AUTO_SWITCH_QUIET_MS
    today = scene_day()
    if assigned_day == today:
        return max(next_day_roll_ms(), quiet_from)
    return max(int(datetime.now().timestamp() * 1000), quiet_from)


def _pick_fresh(exclude_id: str = "") -> Dict[str, str]:
    cards = list_cards()
    cand = [c for c in cards if c.get("id") != exclude_id]
    if not cand:
        cand = cards
    return dict(random.choice(cand)) if cand else {}


def current_for(
    session: Session,
    character_id: int,
    last_user_at: int = 0,
    seed_id: str = "",
    seed_background: str = "",
    seed_day: str = "",
    fresh: bool = False,
) -> Dict[str, Any]:
    """进页唯一入口：记住当天这场，跨过次日 6 点且超过 3 小时没聊才换。"""
    last_ms = _last_user_ms(session, character_id, last_user_at)
    quiet = (not last_ms) or (int(datetime.now().timestamp() * 1000) - last_ms >= AUTO_SWITCH_QUIET_MS)
    row = session.get(SceneState, character_id)
    today = scene_day()

    if fresh:
        card = _pick_fresh(row.scene_id if row else "")
        if not card:
            return {"card": None, "rotated": False, "assigned_day": today, "next_rotate_at": 0}
        save_current(session, character_id, card, today)
        return {
            "card": card, "rotated": True, "assigned_day": today,
            "next_rotate_at": _next_rotate_ms(today, last_ms),
        }

    stored = card_from_row(row)
    if stored and row:
        if row.assigned_day == today or not quiet:
            return {
                "card": stored, "rotated": False, "assigned_day": row.assigned_day,
                "next_rotate_at": _next_rotate_ms(row.assigned_day, last_ms),
            }
        card = _pick_fresh(row.scene_id)
        save_current(session, character_id, card, today)
        return {
            "card": card, "rotated": True, "assigned_day": today,
            "next_rotate_at": _next_rotate_ms(today, last_ms),
        }

    seeded = get_card(seed_id.strip()) if seed_id else None
    if not seeded and seed_background:
        hit = find_by_background(seed_background.strip())
        seeded = dict(hit) if hit else None
    if seeded:
        day = seed_day.strip() if seed_day.strip() else today
        save_current(session, character_id, dict(seeded), day)
        return {
            "card": dict(seeded), "rotated": False, "assigned_day": day,
            "next_rotate_at": _next_rotate_ms(day, last_ms),
        }

    quality = (settings_store.get_all(session).get("quality") or {})
    bg = str(quality.get("background_image") or "")
    from_settings = find_by_background(bg)
    card = dict(from_settings) if from_settings else _pick_fresh()
    if not card:
        return {"card": None, "rotated": False, "assigned_day": today, "next_rotate_at": 0}
    save_current(session, character_id, card, today)
    return {
        "card": card, "rotated": False, "assigned_day": today,
        "next_rotate_at": _next_rotate_ms(today, last_ms),
    }


_BG_RULES = [
    (r"雨|巷|伞", "/backgrounds/bg_alley.png"),
    (r"樱|花瓣|庭院", "/backgrounds/bg_sakura.png"),
    (r"花田|花粉|黄昏花", "/backgrounds/bg_flower.png"),
    (r"海|岸|沙滩|天亮|发灰", "/backgrounds/bg_beach.png"),
    (r"雪", "/backgrounds/bg_snow.png"),
    (r"霓虹|天台|夜城", "/backgrounds/bg_cyber.png"),
    (r"演唱会|侧台|练功|镜子", "/backgrounds/bg_concert.png"),
    (r"灯笼|廊下|古风|殿", "/backgrounds/bg_guofeng.png"),
    (r"宫|台阶|金殿", "/backgrounds/bg_palace.png"),
    (r"咖啡|打烊|冰箱|厨房", "/backgrounds/bg_cafe.png"),
    (r"极光|星空|绿光", "/backgrounds/bg_starry.png"),
    (r"图书|闭馆", "/backgrounds/bg_library.png"),
    (r"林|树|信号", "/backgrounds/bg_forest.png"),
    (r"实验|数据|加班", "/backgrounds/bg_lab.png"),
    (r"祭|烟花|金鱼", "/backgrounds/bg_matsuri.png"),
    (r"云|走廊|高处", "/backgrounds/bg_skycity.png"),
    (r"舷窗|舱|星星", "/backgrounds/bg_space.png"),
    (r"水下|气泡|海宫", "/backgrounds/bg_underwater.png"),
    (r"卧室|吵", "/backgrounds/bg_bedroom.png"),
]


def _background_for(title: str, setting: str) -> str:
    blob = f"{title} {setting}"
    for pat, bg in _BG_RULES:
        if re.search(pat, blob):
            return bg
    pool = [c.get("background") or "" for c in list_cards() if c.get("background")]
    return random.choice(pool) if pool else ""


def _recent_qa_blob(session: Session, character_id: int, limit: int = 6) -> str:
    from ...conversation import SIDE_KINDS
    rows = session.exec(
        select(ChatMessage)
        .where(ChatMessage.character_id == character_id)
        .order_by(ChatMessage.id.desc())
        .limit(24)
    ).all()
    lines: List[str] = []
    for m in reversed(list(rows)):
        if (m.kind or "qa") in SIDE_KINDS:
            continue
        role = "对方" if m.role == "user" else "你"
        text = (m.content or "").strip()
        if not text:
            continue
        lines.append(f"{role}：{text[:80]}")
    return "\n".join(lines[-limit:])


async def generate_tonight(session: Session, character_id: int) -> Dict[str, str]:
    conf = settings_store.get_all(session).get("llm") or {}
    char = session.get(Character, character_id)
    persona = (char.persona if char else "")[:600]
    from ..memory.worker import scene_hints
    loops = scene_hints(character_id)
    recent = _recent_qa_blob(session, character_id)
    hour = datetime.now().hour
    minute = datetime.now().minute
    tod = "凌晨" if hour < 5 else "上午" if hour < 11 else "中午" if hour < 14 else "下午" if hour < 18 else "晚上"
    used = [c["title"] for c in list_cards()]
    blob = await llm_service.complete_json(conf, [
        {"role": "system", "content": (
            "你为 3D 陪玩现编今晚一场戏。只输出 JSON。"
            "这场要能撑住整晚合写，不是一句开场白加一张壁纸。"
            "每次场合、冲突都要新，不许套常见寒暄。"
        )},
        {"role": "user", "content": (
            f"人设：{persona or '温柔带一点撩的虚拟陪玩'}\n"
            f"现在是{tod}，大约{hour}点{minute}分。\n"
            f"记忆里未完的事：{'; '.join(loops) or '无'}\n"
            f"刚才几句对话：\n{recent or '（还没聊过）'}\n"
            f"不要用这些已有标题：{'、'.join(used)}\n"
            "场合要具体到能看见、能闻到、能碰到的细节，不要空泛的『房间里』。"
            "conflict 必须是今晚还没说开的事：可以接记忆或刚才的话现编，不要写成开场台词。"
            "人一进门就已经站在这件事中间。"
            "输出 JSON："
            '{"title":"四字内","setting":"场合一句","conflict":"心里那点事一句",'
            '"opening":"怎么开口的语气一句，不是台词","cam":"close|bust|half|full|threeQ|long",'
            '"intent":"look|tease|think|shy|talk|cute|comfort|relax"}'
            "不要客服腔，不要舞会邀请，不要欢迎回来。"
        )},
    ], max_tokens=400)
    if not isinstance(blob, dict):
        card = dict(random.choice(list_cards()))
        save_current(session, character_id, card)
        return card
    title = str(blob.get("title") or "今晚")[:16]
    setting = str(blob.get("setting") or "")[:120]
    card = {
        "id": f"tonight-{hour:02d}{minute:02d}-{random.randint(10, 99)}",
        "title": title,
        "setting": setting,
        "conflict": str(blob.get("conflict") or "")[:120],
        "opening": str(blob.get("opening") or "像刚看见对方那样随口接。")[:80],
        "cam": str(blob.get("cam") or "half"),
        "intent": str(blob.get("intent") or "look"),
        "background": _background_for(title, setting),
    }
    save_current(session, character_id, card)
    return card
