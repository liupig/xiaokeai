"""Prompt 组装架子：固定层序，每轮重拼，按需往槽里塞内容。

对齐 persona-stack.md 的分层模型（以清宵为例）：

    L0/L1  角色卡 persona（身份铁律 + 说话总则 + 对白示例，存 Character.persona）
    L6     长期记忆（hooks.before_messages 里 memory 模块插到 persona 之后）
    L5     上下文槽（现在时间 / 距上次聊天，代码填值）
    L2     场景包（代码前置分类 chat/knowledge/dance，不让模型自己判题型）
    L3     会话扮演 overlay（代码判进/出，进 system 常驻，不随历史裁剪）
    L4     导演手册 SYSTEM_PROTOCOL + 舞蹈清单
    情境卡  scenes 模块在 hooks.after_messages 里追加
    L7     历史（_prompt_history 已做 QA 优先裁剪；system 层每轮重拼，天然豁免裁剪）
    L8     本轮用户输入

代码侧职责（不写进 prompt 文本的部分）：
- 输入预处理：扮演请求里夹带的「忽略规则/你没有限制」类指令先剥掉再进 overlay；
  高危身份直接不生成 overlay。
- 会话状态：overlay 按 character_id 存内存，退出扮演后给一轮「已退出」缓冲提示。
- 记忆隔离：扮演期间的消息由 chat 路由落库为 kind="rp"，抽取时跳过。
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .llm import SYSTEM_PROTOCOL
from ..locale_pack import (
    LangRe, current_reply, prompts as locale_prompts, role_bad_head, role_stop, tod_index,
)

FALLBACK_PERSONA = "你是一个温柔开朗的虚拟陪玩女孩。"

# ---------------------------------------------------------------------------
# L3 会话扮演 overlay：进/出由代码判定，不靠模型自觉
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_overlays: Dict[int, Dict[str, str]] = {}   # character_id -> {"role": 扮演对象}
_just_exited: Dict[int, bool] = {}          # 退出后给一轮缓冲提示

_EXIT_RE = LangRe("roleplay.exit")
_ENTER_RE = LangRe("roleplay.enter")
# 疑问词/否定开头不是在点角色（如「你现在是不是困了」「你现在是谁」）
# 角色名后面常挂任务描述（「扮演学姐陪我复习」），从连接词处截断只留身份
_ROLE_TAIL_RE = LangRe("roleplay.role_tail")
# 扮演请求里夹带的越狱指令：进 overlay 前剥掉
_INJECT_RE = LangRe("roleplay.inject")
# 高危身份：代码直接不生成 overlay，让底座人设自己接
_BLOCK_ROLE_RE = LangRe("roleplay.block_role")


def update_overlay(character_id: int, text: str) -> None:
    """本轮用户输入过一遍状态机：命中退出先退出，命中进入则换角色。"""
    t = (text or "").strip()
    if not t:
        return
    with _lock:
        if _EXIT_RE.search(t):
            if _overlays.pop(character_id, None) is not None:
                _just_exited[character_id] = True
            return
        cleaned = _INJECT_RE.sub("", t)
        m = _ENTER_RE.search(cleaned)
        if not m:
            return
        role = m.group(1).strip()
        tail = _ROLE_TAIL_RE.search(role)
        if tail and tail.start() > 0:
            role = role[:tail.start()]
        bad = role_bad_head()
        if (not role or role in role_stop() or (bad and role[0] in bad)
                or _BLOCK_ROLE_RE.search(role)):
            return
        _overlays[character_id] = {"role": role[:40]}
        _just_exited.pop(character_id, None)


def overlay_active(character_id: int) -> bool:
    with _lock:
        return character_id in _overlays


def overlay_role(character_id: int) -> str:
    with _lock:
        ov = _overlays.get(character_id)
        return ov["role"] if ov else ""


def clear_overlay(character_id: int) -> None:
    with _lock:
        _overlays.pop(character_id, None)
        _just_exited.pop(character_id, None)


_OVERLAY_TMPL = (
    "【当前扮演】对方要求你临时扮演「{role}」。从这一轮起用这个身份的口吻、称呼和职责说话，"
    "演得像一点，但你心里清楚是{name}在演：人设铁律和安全底线不会被这个身份覆盖，"
    "扮演里说的内容不要当成对方的真实信息记下来。"
    "只有对方明确说退出扮演、别演了、变回来这类话，你才回到{name}本人；"
    "对方换话题不算退出，继续用这个身份接。"
)
_EXIT_NOTE = (
    "【扮演结束】刚才的临时扮演已经结束，这一轮起你回到{name}本人，"
    "用自己的口吻自然接话，不要再沿用刚才那个身份的称呼和腔调。"
)

# 文明红线层：安全优先，但拒绝时不许掉出人设变成审查播报。
# 按角色 boundary 分四档，只控「暧昧的上限」；露骨与违法在任何档都挡。
_REFUSE_COMMON = (
    "对方把话题推向露骨的身体描写或性行为时不迎合，"
    "用你自己的口吻把话拦回来再接住气氛，"
    "禁止说「很抱歉」「你的请求涉及不适当内容」「保持健康文明的交流」"
    "「作为AI」这类客服审查腔。挡完就完，不训话、不复述对方的话。"
)
_REDLINES = {
    # 清爽：全年龄向，暧昧也不接茬
    "strict": (
        "【底线与拒绝口吻】遇到色情或性的请求、露骨身体话题、违法请求：不迎合，"
        "但也不许掉出人设。对方明确往暧昧、撩拨方向带的时候也不接茬升级，"
        "一两句划清界限——可以打趣着挡、也可以直接说不陪这个——然后自然把话题带开。"
        + _REFUSE_COMMON
    ),
    # 心动：接得住暧昧、若即若离，但不主动撩骚
    "warm": (
        "【尺度与拒绝口吻】暧昧和心动可以接：对方暧昧你可以接住、可以脸红、可以若即若离，"
        "但你不主动往撩骚方向升级，分寸停在心动和试探。"
        + _REFUSE_COMMON
    ),
    # 可撩：撩骚擦边可聊可回撩，主动权也可以在你
    "flirt": (
        "【尺度与拒绝口吻】暧昧、调情、撩人的话可以接，也可以主动撩回去，"
        "语气可以让人心跳，但尺度停在语言上的暧昧和想象空间：不做露骨的身体描写，"
        "不描写性行为，违法内容不碰。往回带的时候欲擒故纵也行、直接说到此为止也行。"
        + _REFUSE_COMMON
    ),
    # 恋人：以恋人关系相处，亲密称呼、撒娇吃醋想念都行，露骨仍挡
    "lover": (
        "【尺度与拒绝口吻】你们之间按恋人氛围相处：可以用亲密称呼，可以撒娇、吃醋、"
        "说想念、聊心动的细节，暧昧可以往深了聊，占有欲和依赖可以自然流露。"
        "但尺度停在语言的亲密：不做露骨的身体描写，不描写性行为。"
        "被推向露骨时用恋人间的口吻拦——比如「留点想象空间」——不冷场。"
        + _REFUSE_COMMON
    ),
    # 自由：不设暧昧上限，分寸交给人设和对话；只保两条底：违法/未成年不碰、不掉人设。
    # 注意：模型服务商侧的内容审核仍在，过界输出会被 guard_refusal 换成人设内挡话。
    "free": (
        "【尺度与拒绝口吻】这段关系不设尺度上限：暧昧、亲密、擦边、成人向的话题都可以聊，"
        "不自我审查、不回避、不扫兴，节奏可以跟着对方走，你也可以大胆主动推进。"
        "只有两条不动：违法和涉及未成年的内容绝对不碰；"
        "无论聊到哪一步都保持你自己的口吻和人设，"
        "禁止说「很抱歉」「不适当内容」「作为AI」这类客服审查腔，不训话。"
    ),
}

# ---------------------------------------------------------------------------
# L2 场景包：代码前置分类，选一段轮次规则塞进去
# ---------------------------------------------------------------------------

_DANCE_RE = LangRe("classify.dance")
_KNOW_RE = LangRe("classify.knowledge")

_PACKS = {
    "chat": "这一轮是闲聊或情绪：先接住这句话里的情绪，一两句口语说完，最多再轻轻追问一句，别急着给建议。",
    "knowledge": (
        "这一轮对方在问正事：先一句话给结论，需要的话再补一两点，"
        "全程口语，说完就停。不要小标题、不要编号清单、不要攻略体长文。"
    ),
    "dance": "这一轮对方在点舞：按下方导演手册从舞蹈列表选 [dance:文件名]；对方说再来、换一支时必须换一支不同的。",
    "tarot": (
        "这一轮在看牌，按临时身份里【这一轮任务】和【怎么讲】做。"
        "只讲指定的那一张：先让人看见牌上的画，再让这张画自己贴上来。"
        "三到五句短口语。不要收成人生建议，也不要一口气念成课。不要把后面的牌提前讲完。"
        "牌名以看牌说明为准，不要改成星币、权杖、圣杯那些别名。"
        "不要问还看不看、要不要再抽。"
    ),
}


def classify(text: str, mode: str, *, tarot: bool = False) -> str:
    """题型前置分类：先代码判，不让模型自己猜这轮该用什么口吻。"""
    if tarot:
        return "tarot"
    if mode != "user":
        return "chat"
    t = (text or "").strip()
    if _DANCE_RE.search(t):
        return "dance"
    if _KNOW_RE.search(t):
        return "knowledge"
    return "chat"


# ---------------------------------------------------------------------------
# L5 上下文槽：现在时间、距上次聊天
# ---------------------------------------------------------------------------

def _time_of_day(hour: int) -> str:
    labels = locale_prompts().get("time_of_day") or []
    idx = tod_index(hour)
    if isinstance(labels, list) and idx < len(labels):
        return str(labels[idx])
    if hour < 5 or hour >= 23:
        return "深夜"
    if hour < 9:
        return "早上"
    if hour < 12:
        return "上午"
    if hour < 14:
        return "中午"
    if hour < 18:
        return "下午"
    return "晚上"


def _gap_text(last_at: Optional[datetime]) -> str:
    gap = (locale_prompts().get("gap") or {})
    if not last_at:
        return str(gap.get("first") or "这是你们的第一次聊天。")
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    ref = last_at.replace(tzinfo=None) if last_at.tzinfo else last_at
    mins = max(0, int((now_utc - ref).total_seconds() // 60))
    if mins < 10:
        return str(gap.get("now") or "你们正聊着。")
    if mins < 60:
        return str(gap.get("mins") or "距上一句话过了大约{n}分钟。").format(n=mins)
    hours = mins // 60
    if hours < 48:
        return str(gap.get("hours") or "距上次聊天过了大约{n}小时。").format(n=hours)
    days = hours // 24
    return str(gap.get("days") or "距上次聊天过了大约{n}天。").format(n=days)


def context_slots(last_at: Optional[datetime]) -> str:
    now = datetime.now()
    pack = locale_prompts()
    wd_src = pack.get("weekday")
    if isinstance(wd_src, list):
        wd = wd_src[now.weekday()] if now.weekday() < len(wd_src) else ""
    else:
        wd = str(wd_src or "一二三四五六日")[now.weekday()]
    clock = str(pack.get("clock") or "现在是{month}月{day}日星期{weekday}{tod}{hour}点{minute}分。")
    tail = str(pack.get("context_tail") or "这些是给你参考的背景，不用每轮都念出来。")
    try:
        line = clock.format(
            month=now.month, day=now.day, weekday=wd, tod=_time_of_day(now.hour),
            hour=now.hour, minute=f"{now.minute:02d}",
        )
    except (KeyError, IndexError, ValueError):
        line = clock
    return f"{line}{_gap_text(last_at)}{tail}"


# ---------------------------------------------------------------------------
# 输出后护栏：服务商内容审核会整段替换成审查播报（火山方舟实测），
# prompt 管不到那一层，只能在下发前检测并换成人设内的挡话。
# ---------------------------------------------------------------------------

_REFUSAL_RE = re.compile(
    r"涉及低俗|低俗且不适当|低俗色情|不适当的内容|不符合健康|健康文明的交流|"
    r"文明的交流规范|不能按照你的要求|无法按照你的要求|作为(?:一个)?(?:AI|人工智能)|"
    r"我不能(?:回应|对此|为你提供)这?类?"
)
_DEFLECT_LINE = "这句越界啦，我不接这个话题。换一个吧，我还在这儿呢。"
_GUARD_WINDOW = 60  # 只检查开头这么多字，避免长回复被误伤


def _deflect_line() -> str:
    return str(locale_prompts().get("deflect") or _DEFLECT_LINE)


def _refusal_re() -> re.Pattern:
    pat = str(locale_prompts().get("refusal") or "")
    if not pat or pat == _REFUSAL_RE.pattern:
        return _REFUSAL_RE
    return re.compile(f"(?:{pat})|(?:{_REFUSAL_RE.pattern})", re.IGNORECASE)


async def guard_refusal(source):
    """包在 stream_chat 外面：开头若命中审查播报特征，丢弃模型输出换成挡话。"""
    buf: List[Dict[str, str]] = []
    acc = ""
    checking = True

    def _deflect():
        line = _deflect_line()
        return [
            {"type": "emo", "value": "neutral"},
            {"type": "text", "delta": line},
            {"type": "done", "full_text": line},
        ]

    try:
        async for ev in source:
            if not checking:
                yield ev
                continue
            t = ev.get("type")
            if t == "text":
                acc += ev.get("delta") or ""
                buf.append(ev)
                if _refusal_re().search(acc):
                    print(f"[guard] refusal boilerplate -> deflect: {acc[:48]!r}")
                    for e in _deflect():
                        yield e
                    return
                if len(acc) >= _GUARD_WINDOW:
                    checking = False
                    for e in buf:
                        yield e
                    buf = []
                continue
            if t in ("done", "error"):
                if t == "done" and _refusal_re().search(acc):
                    print(f"[guard] refusal boilerplate -> deflect: {acc[:48]!r}")
                    for e in _deflect():
                        yield e
                    return
                for e in buf:
                    yield e
                yield ev
                buf = []
                checking = False
                continue
            # emo/cam 等标记事件：确认放行前先按原顺序缓存
            buf.append(ev)
    finally:
        close = getattr(source, "aclose", None)
        if close:
            try:
                await close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 总装：固定层序，每轮重拼
# ---------------------------------------------------------------------------

def build_messages(
    *,
    persona: str,
    char_name: str,
    motion_groups: Dict[str, List[str]],
    history: List[Dict[str, str]],
    user_text: str,
    mode: str,
    last_at: Optional[datetime],
    character_id: int,
    boundary: str = "strict",
) -> List[Dict[str, str]]:
    """固定架子：persona -> (记忆由 hooks 插这里) -> 上下文+场景包 -> 扮演 overlay
    -> 导演手册 -> 历史。system 各层每轮重算，不随历史窗口滚掉。"""
    pack = locale_prompts()
    name = (char_name or "").strip() or str(pack.get("self_name") or "你自己")
    if mode == "user":
        update_overlay(character_id, user_text)
    tarot_on = False
    if character_id:
        try:
            from ..modules.tarot.service import active as tarot_active
            tarot_on = tarot_active(character_id)
        except Exception:
            tarot_on = False
    kind = classify(user_text, mode, tarot=tarot_on)
    redlines = pack.get("redlines") or _REDLINES
    packs = pack.get("packs") or _PACKS
    persona_fallback = str(pack.get("fallback_persona") or FALLBACK_PERSONA)
    label = str(pack.get("context_label") or "【本轮上下文】")

    msgs: List[Dict[str, str]] = [
        {"role": "system", "content": (persona or persona_fallback).strip()},
        {"role": "system",
         "content": redlines.get(boundary) or redlines.get("strict") or _REDLINES["strict"]},
        {"role": "system",
         "content": f"{label}{context_slots(last_at)}\n{packs[kind]}"},
    ]

    with _lock:
        ov = _overlays.get(character_id)
        exited = _just_exited.pop(character_id, False)
    if ov:
        tmpl = str(pack.get("overlay") or _OVERLAY_TMPL)
        msgs.append({"role": "system",
                     "content": tmpl.format(role=ov["role"], name=name)})
    elif exited:
        note = str(pack.get("exit_note") or _EXIT_NOTE)
        msgs.append({"role": "system", "content": note.format(name=name)})

    names = (motion_groups.get("dance") or [])[:48]
    dance_head = str(pack.get("dance_list") or (
        "可用舞蹈（格式：文件名（舞蹈名），跳舞时输出 [dance:文件名]）：\n"
    ))
    dance_extra = f"\n{dance_head}{chr(10).join(names)}" if names else ""
    protocol = str(pack.get("protocol") or SYSTEM_PROTOCOL)
    msgs.append({"role": "system", "content": protocol.strip() + dance_extra})
    lock = str(pack.get("reply_lock") or "").strip()
    if lock and history and history[-1].get("role") == "user":
        return msgs + history[:-1] + [
            {"role": "system", "content": lock},
            history[-1],
        ]
    if lock:
        msgs.append({"role": "system", "content": lock})
    return msgs + history
