"""要不要把这一轮交给 dsh，以及【现场】里放什么。

路由不在这里做。这里只决定宿主哪几轮改走 harness，以及技能正文以外的数据。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

# 模型只看最近十轮（对方一句、她一句算一轮）。更早的留在宿主记录里，不进这条会话。
RECENT_ROUNDS = 10
_DANCE_ASK = re.compile(r"跳.{0,6}舞|舞蹈|来一支|再来一支|换一支|再跳一次|再跳一下")
_DANCE_AGAIN = re.compile(r"再跳一次|再跳一下|再来一次|再来一支")
_DANCE_SWITCH = re.compile(r"换一个|换一支|换个舞")


def wants_harness(
    *,
    enabled: bool,
    mode: str,
    reroll: bool = False,
    afterglow: bool = False,
) -> bool:
    """用户开口进 dsh。看牌进行中的那句也进，目录才能选中 tarot。

    陪我看时，画面变了的那句也进同一条会话。牌仍由代码发。
    收摊后那句、重说、宿主按沉默排的句子仍走旧管线。
    """
    return bool(enabled) and mode in ("user", "along") and not reroll and not afterglow


def host_brief(messages: Sequence[Dict[str, str]], dance_names: Sequence[str] | None = None) -> str:
    """从已经叠好的提示里留下身份和场合。导演手册留在 chat 技能正文里。"""
    parts: List[str] = []
    for message in messages:
        if (message.get("role") or "") != "system":
            continue
        content = (message.get("content") or "").strip()
        if not content:
            continue
        if "[emo:happy]" in content and "[dance:]" in content:
            continue
        parts.append(content)
    names = [name.strip() for name in (dance_names or []) if str(name).strip()]
    reading = any("【当前扮演】" in part or "【这一轮任务】" in part for part in parts)
    if names and not reading:
        parts.append("可用舞蹈（文件名）：\n" + "\n".join(names[:48]))
    return "\n\n".join(parts)


def wish_recall(content: str) -> str:
    """许愿是本地念的，不进会话记录。把库里那一条交给这一轮。"""
    text = (content or "").strip()
    if text.startswith("[wish]"):
        text = text[len("[wish]") :].strip()
    if not text:
        return ""
    return (
        "补充现在的记忆，身份和规矩仍按会话开头。\n"
        "最近一次许愿（以这句为准，更早的许愿记录作废）："
        + text
        + "对方问起扔进了什么、落下多少金币，按这句说，不要改数字。没问就不要提。"
    )


def _prior_danced(prior: Sequence[Dict[str, str]] | None) -> bool:
    for message in reversed(list(prior or [])):
        if (message.get("role") or "") != "assistant":
            continue
        text = message.get("content") or ""
        return "[dance:" in text or "舞" in text
    return False


def dance_opening(user_text: str, prior: Sequence[Dict[str, str]] | None = None) -> str:
    """点舞时先把这一句说出去。技能回来后再补后一句。"""
    raw = re.sub(r"\s+", "", user_text or "")
    if not raw or len(raw) > 40:
        return ""
    again = bool(_DANCE_AGAIN.search(raw))
    switch = bool(_DANCE_SWITCH.search(raw))
    asked = bool(_DANCE_ASK.search(raw))
    if again and "再来一次" in raw and not _prior_danced(prior) and not asked:
        again = False
    if switch and not asked and not _prior_danced(prior):
        return ""
    if not asked and not again and not switch:
        return ""
    if again:
        return "好，再来一次。"
    if switch:
        return "好，换一支。"
    return "好，我跳一支。"


def turn_text(
    *,
    brief: str,
    user_text: str,
    prior: Sequence[Dict[str, str]] | None = None,
    recall: str = "",
) -> str:
    chunks: List[str] = []
    lines: List[str] = []
    for message in prior or []:
        role = (message.get("role") or "").strip()
        content = (message.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        who = "她" if role == "assistant" else "对方"
        lines.append(f"{who}：{content}")
    if lines:
        chunks.append("【刚说过】\n" + "\n".join(lines[-(RECENT_ROUNDS * 2) :]))
    field = (brief or "").strip()
    note = (recall or "").strip()
    if note:
        field = f"{field}\n\n{note}".strip() if field else note
    if field:
        chunks.append("【现场】\n" + field)
    from ..draw.service import user_draw_scene
    line = (user_text or "").strip()
    opening = dance_opening(user_text, prior)
    if opening:
        line += f"\n（铺垫已经说了：{opening}不要重复。先调用 dance 技能，回来后再补一句，并写 [dance:]。不要说技能。）"
    if user_draw_scene(user_text, prior):
        line += "\n（这句已经在画了，第一句也说了。不要写 [draw:]，不要重复「我来画」。可以补一句画面里有什么。不要说画好了。）"
    chunks.append("【这句】\n" + line)
    return "\n\n".join(chunks)


def chunk_text_delta(event: Dict[str, Any]) -> str | None:
    """流式正文。推理和工具参数不算要念的话。"""
    if (event.get("type") or "") != "assistant/chunk":
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    chunk = data.get("chunk")
    if not isinstance(chunk, dict) or chunk.get("type") != "text-delta":
        return None
    return str(chunk.get("text") or "")


def assistant_text(event: Dict[str, Any]) -> str | None:
    """从一条 session 事件里取出助手正文。没有正文就返回 None。"""
    if (event.get("type") or "") != "assistant/message":
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    message = data.get("message")
    owner = message if isinstance(message, dict) else data
    content = owner.get("content")
    if not isinstance(content, list):
        return None
    parts: List[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts)


class TextGrowth:
    """同一条助手消息变长时，只交出新增的那段。流式片段先交，整句到了不再重复。"""

    def __init__(self) -> None:
        self._by_id: Dict[str, str] = {}
        self._live = ""
        self.emitted = ""

    def feed(self, event: Dict[str, Any]) -> str:
        piece = chunk_text_delta(event)
        if piece:
            self._live += piece
            self.emitted += piece
            return piece
        if (event.get("type") or "") == "assistant/chunk":
            return ""
        text = assistant_text(event)
        if text is None:
            return ""
        if self._live:
            extra = text[len(self._live) :] if text.startswith(self._live) else ""
            self._live = ""
            if not extra:
                return ""
            self.emitted += extra
            return extra
        key = str(event.get("id") or "assistant")
        prev = self._by_id.get(key, "")
        self._by_id[key] = text
        if text.startswith(prev):
            delta = text[len(prev):]
        elif not prev:
            delta = text
        else:
            delta = text
        if not delta:
            return ""
        self.emitted += delta
        return delta

    def finish(self, final: str) -> str:
        final = final or ""
        if not final:
            return ""
        if final.startswith(self.emitted):
            return final[len(self.emitted):]
        if self.emitted:
            return ""
        return final


_LEAK = re.compile(
    r"技能|skill|system-reminder|available_skills|diagnose-windows|"
    r"用户现在说|系统提示|可用的是|列表里",
    re.IGNORECASE,
)
_SPOKEN_END = re.compile(r"[。！？!?\n～~]")


def _catalog_talk(sentence: str) -> bool:
    return bool(_LEAK.search(sentence or ""))


class SpokenGate:
    """技能目录和自我推理不要进语音。收成一句再决定放不放。"""

    def __init__(self) -> None:
        self.buf = ""

    def feed(self, delta: str) -> str:
        self.buf += delta or ""
        kept: List[str] = []
        while True:
            mark = _SPOKEN_END.search(self.buf)
            if not mark:
                break
            sentence = self.buf[: mark.end()]
            self.buf = self.buf[mark.end() :]
            if sentence.strip() and not _catalog_talk(sentence):
                kept.append(sentence)
        return "".join(kept)

    def flush(self) -> str:
        rest = self.buf
        self.buf = ""
        if rest.strip() and not _catalog_talk(rest):
            return rest
        return ""
