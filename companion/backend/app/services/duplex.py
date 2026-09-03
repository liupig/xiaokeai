"""全双工对话节奏（小冰 Jarvis Processor / Transaction 侧）。

不负责 ASR/TTS 模型本身：只把回复切成 PlayableUnit，并打上 DuplexCmd / SentenceType。
真正合成音频由 /api/speech/tts 在 ChannelPool 决定「要播」之后才发生（Skip 的句子不会去占 GPU）。
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Tuple

from .narration import peel_stage_dirs
from .speech_split import SentenceSplitter

BODY_CMDS = {
    "queue", "interrupt", "interrupt_or_queue",
    "conditional_queue", "conditional_interrupt",
}
FILLER_TEXTS = ("嗯…", "我看看…", "稍等…")

CONTINUE_HINT = (
    "用户这轮暂时没再说话。现在是「超时续聊」：你要主动把对方聊起来。"
    "必须做到：\n"
    "1. 开口只能是口语，一两句，最后用一个轻松追问（带「吗／呢／要不要／还是」），接刚才的话题。\n"
    "2. 表演只用标记：[emo:…] [intent:…]，不要写小说旁白。"
    "这是半身闲聊：优先 [cam:half] [intent:tease] [intent:look] [intent:nod] [intent:greet]，"
    "不要鞠躬、坐下、跳舞，不要连切镜头。\n"
    "3. 禁止把动作写成正文。错：「轻轻转了下手腕上的细镯子」「抬手给自己倒了杯温茶」——"
    "这种句子会被念出来，而且不会触发动作。对：「[emo:relaxed][intent:tease]还在想刚才那句？还是想听我再贫两句？」\n"
    "4. 不要重复上一句，不要自言自语。"
    "禁止输出 [dance:]，禁止邀请完整跳舞、换舞、再跳一段。"
    "对方如果刚看完或正在看表演，只口头接话追问，不要再开一支舞。"
)

PROACTIVE_HINT = (
    "双方都沉默了一会儿。这是「主动搭话 Proactive」：再轻轻叫一声对方，换个角度追问，"
    "一两句口语，带 [emo:] [intent:look] 或 [intent:tease]。"
    "保持半身 [cam:half]，不要 [dance:]，不要挥手鞠躬，不要旁白描写。"
)

GOODBYE_HINT = (
    "会话要结束了。这是「告别 Goodbye」：用一句很短的口语道别，"
    "带 [emo:] [intent:nod] 或 [intent:look]。表情道别即可，不要挥手鞠躬、不要必须拉远。"
    "不要提问，不要邀舞，不要旁白，不要说「超时」「会话结束」。"
)

CONTINUE_IN_SCENE = (
    "用户这轮暂时没再说话。这是超时续聊：一两句口语，最后轻轻追问。"
    "不要旁白，不要 [dance:]，不要重复上一句。"
    "场合和镜头见后面的情境，不要切回空白半身闲聊。"
)

PROACTIVE_IN_SCENE = (
    "双方沉默了一会儿。再轻轻接一句，换个角度追问。"
    "一两句口语。不要旁白，不要 [dance:]。"
    "场合和镜头见后面的情境，不要切回空白半身闲聊。"
)

WELCOME_HINT = (
    "对方刚打开页面，这是会话开头「Welcome」。用户这轮还没说话。"
    "你要像真人刚看见对方那样随口接一句，不要念稿。"
    "必须做到：\n"
    "1. 先看聊天记录：有往来就顺着上次的情绪和话题轻轻接（调侃、关心、补一句都行），"
    "不要复述剧情，不要「欢迎回来」「好久不见」这种客服腔。\n"
    "2. 没记录就按人设和此刻心情开口，像碰巧对上眼，不要自我介绍，不要「你好我是谁」。\n"
    "3. 绝对禁止使用角色卡打招呼语、欢迎词、固定开场白，也不要「想聊天还是想看跳舞」。\n"
    "4. 一两句口语，带 [emo:] [intent:look] 或 [intent:tease] 或 [intent:nod]。"
    "半身 [cam:half] 就好，不要一上来挥手或拉全身。"
    "如果上一条已经是你的开场，换个说法，不要连着打招呼。"
    "禁止 [dance:]，禁止旁白描写，禁止提问清单。"
)

# 超时续聊里常见的「演戏旁白」，不应进 TTS
_NARRATION_START = re.compile(
    r"^(轻轻[地]?|微微|抬手|伸手|低头|侧过|转过|给自己|为自己|"
    r"倒了杯|端起|抿了|眨了眨眼|笑了笑|把玩|摩挲|拂了拂|"
    r"抬眼|垂眸|撑着腮|托着腮|脑袋一歪|歪着头|凑过来|蹭了蹭|"
    r"一头扎|撞进你)"
)


def strip_spoken_narration(text: str) -> str:
    """去掉第三人称动作描写，只留能说出口的句子。"""
    parts = re.split(r"(?<=[。！？!?；;\n])", text or "")
    keep: List[str] = []
    for part in parts:
        s = part.strip()
        if not s:
            continue
        if "？" in part or "?" in part:
            keep.append(part)
            continue
        if _NARRATION_START.search(s):
            continue
        keep.append(part)
    return "".join(keep).strip()


def normalize_body_cmd(v: Any) -> str:
    s = str(v or "").strip().lower()
    return s if s in BODY_CMDS else "interrupt_or_queue"


def tag_for_kind(kind: str, body_cmd: str = "interrupt_or_queue") -> Tuple[str, str]:
    """返回 (duplex_cmd, sentence_type)。"""
    k = (kind or "body").lower()
    cmd = normalize_body_cmd(body_cmd)
    if k == "filler":
        return "intermediate", "transition"
    if k == "delayed":
        return "skip_on_new", "transition"
    if k == "proactive":
        return "skip_on_new", "proactive"
    if k == "welcome":
        return "skip_on_new", "welcome"
    if k == "goodbye":
        return "skip_on_new", "goodbye"
    if k == "phrase":
        return cmd, "normal"
    return cmd, "normal"


def make_unit(text: str, kind: str, body_cmd: str = "interrupt_or_queue") -> Dict[str, Any]:
    cleaned, _extras = peel_stage_dirs(text or "")
    cleaned = strip_spoken_narration(cleaned)
    cmd, stype = tag_for_kind(kind, body_cmd)
    return {
        "type": "speech",
        "id": uuid.uuid4().hex[:12],
        "text": cleaned,
        "duplex_cmd": cmd,
        "sentence_type": stype,
        "kind": kind,
        "update_context": cmd != "skip",
    }


async def annotate_stream(
    events,
    *,
    body_cmd: str = "interrupt_or_queue",
    filler: bool = True,
    delayed_sec: float = 6,
    unit_kind: str = "body",
):
    """把 LLM 异步事件流补上 speech 单元。text 仍给 UI；合成只走 speech。"""
    splitter = SentenceSplitter()
    body_cmd = normalize_body_cmd(body_cmd)
    first_body = True
    try:
        async for ev in events:
            if ev.get("type") == "text":
                yield ev
                kind = unit_kind if unit_kind != "body" else ("phrase" if first_body else "body")
                for sent in splitter.feed(ev.get("delta") or ""):
                    spoken, extras = peel_stage_dirs(sent)
                    for extra in extras:
                        yield extra
                    unit = make_unit(spoken, kind, body_cmd)
                    if unit["text"]:
                        yield unit
                    first_body = False
                    if unit_kind == "body":
                        kind = "body"
                continue
            if ev.get("type") == "done":
                kind = unit_kind if unit_kind != "body" else ("phrase" if first_body else "body")
                for sent in splitter.flush():
                    spoken, extras = peel_stage_dirs(sent)
                    for extra in extras:
                        yield extra
                    unit = make_unit(spoken, kind, body_cmd)
                    if unit["text"]:
                        yield unit
                    first_body = False
                    if unit_kind == "body":
                        kind = "body"
                yield ev
                sec = float(delayed_sec or 0)
                if sec > 0:
                    yield {"type": "duplex", "delayed_sec": sec}
                continue
            yield ev
    finally:
        close = getattr(events, "aclose", None)
        if close:
            try:
                await close()
            except Exception:
                pass


def duplex_conf(conf: Dict[str, Any]) -> Dict[str, Any]:
    tts = conf.get("tts") or {}
    remain = tts.get("duplex_remain_sec", 3)
    delayed = tts.get("duplex_delayed_sec", 16)
    filler = tts.get("duplex_filler", True)
    return {
        "body_cmd": normalize_body_cmd(tts.get("duplex_cmd")),
        "remain_sec": float(remain) if remain not in (None, "") else 3,
        "delayed_sec": float(delayed) if delayed not in (None, "") else 16,
        "proactive_sec": float(tts["duplex_proactive_sec"]) if tts.get("duplex_proactive_sec") not in (None, "") else 45,
        "goodbye_sec": float(tts["duplex_goodbye_sec"]) if tts.get("duplex_goodbye_sec") not in (None, "") else 140,
        "session_max_min": float(tts["duplex_session_max_min"]) if tts.get("duplex_session_max_min") not in (None, "") else 0,
        "filler": False,
    }
