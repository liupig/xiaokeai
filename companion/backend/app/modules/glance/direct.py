"""陪看单次自然交流生成与零延迟校验。"""
from __future__ import annotations

import asyncio
import os
import re
from contextlib import aclosing

MOODS = ("紧张", "搞笑", "温馨", "悲伤", "燃", "尴尬", "无聊", "平静")
_EMO = {
    "紧张": "neutral", "搞笑": "happy", "温馨": "relaxed", "悲伤": "sad",
    "燃": "happy", "尴尬": "neutral", "无聊": "relaxed", "平静": "neutral",
}
_SILENT = {"silent", "[silent]", "不说", "不说。", "没变", "没有", "沉默", "保持沉默"}
_META = re.compile(
    r"不吵你|不插嘴|不催|不重复|挨着你|贴着你|陪着你|我陪你|静静陪|慢慢看|"
    r"等下一|等新|等它|等画面|等门|有新动静|有新画面|有自然反应|继续看下去|接着往下看"
)


def enabled() -> bool:
    return (os.environ.get("XIAOKE_ALONG_DIRECT") or "1").strip().lower() not in {"0", "false", "off", "no"}


def generator() -> str:
    override = (os.environ.get("XIAOKE_ALONG_DIRECT_GENERATOR") or "").strip().lower()
    if override in {"minicpm", "chat"}:
        return override
    try:
        import json
        from sqlmodel import Session
        from ...db import engine
        from ...models import Setting
        with Session(engine) as session:
            row = session.get(Setting, "vision")
        value = str((json.loads(row.value) if row else {}).get("generator") or "chat").lower()
    except Exception:
        value = "chat"
    return value if value in {"minicpm", "chat"} else "chat"


def instruction(talk: str = "normal") -> str:
    amount = "可以多一点主动，但仍只自然说一两句。" if talk == "more" else "自然说一两句，不超过45字。"
    return (
        "你正和他一起经历当前内容，不是画面解说员。从当前事件和最近前情里，选一个最值得交流的点。"
        "可以接人物情绪、关系、笑点、疑问、你的偏好或一个相关的小问题；可以接着刚才的话题往前走。"
        "不要描述识别过程，不要播报画面变化，不要说你在陪伴、等待、安静或不重复。"
        "不要复述上一句，不要硬扯舞台和人设，不要编未经确认的剧情。" + amount + "\n"
        "如果没有新理解或值得交流的话，只输出：不说。否则只输出自然台词，不要标签、分析或格式说明。"
    )


def company_instruction() -> str:
    return (
        "你们安静相处了一会儿。可以根据共同看过的内容、他没接的话头或你们的关系，自然找一句话。"
        "优先接着一个具体话题，不要播报‘我陪着你/我不吵你’，不要问空泛的‘你在想什么’。"
        "不超过45字。没有自然的话只输出：不说。"
    )


def visual_instruction() -> str:
    return (
        "按时间顺序理解这段连续视频，只记录当前实际可见的一件关键事实。"
        "没有实质变化就写没变，不换一种说法重复旧事实，不生成台词，不评价。\n"
        "只输出两行：\n画面：当前主体和动作，没有变化就写没变\n经过：本段明确的新变化，没有就留空"
    )


def parse_natural(raw: str) -> dict:
    text = re.sub(r"\[[a-z]+(?::[^\]]*)?\]", "", raw or "", flags=re.I).strip()
    text = re.sub(r"^\s*```(?:text)?\s*|\s*```\s*$", "", text, flags=re.I).strip()
    if text.casefold() in _SILENT:
        return {"action": "silent", "text": ""}
    text = re.sub(r"^(台词|回复|回答)\s*[：:]\s*", "", text).strip()
    if text.casefold() in _SILENT or not text:
        return {"action": "silent", "text": ""}
    if len(re.sub(r"\s+", "", text)) > 45:
        return {"action": "protocol", "problem": "line_too_long", "text": ""}
    return {"action": "speak", "text": text}


def _mood(text: str) -> str:
    if re.search(r"哈哈|好笑|笑死|有趣|太会|好玩|乐", text):
        return "搞笑"
    if re.search(r"扎心|难过|心疼|想哭|难受|虐", text):
        return "悲伤"
    if re.search(r"暖|温柔|安心|幸福|甜", text):
        return "温馨"
    if re.search(r"急|紧张|担心|害怕|压迫|别|快", text):
        return "紧张"
    if re.search(r"燃|帅|痛快|漂亮|厉害", text):
        return "燃"
    return "平静"


def parse_protocol(raw: str) -> dict:
    fields = {}
    for label in ("情绪", "值不值得说", "台词"):
        matched = re.search(rf"^\s*{label}\s*[：:]\s*(.*)\s*$", raw or "", re.M)
        if not matched:
            return {"action": "protocol", "problem": f"missing_{label}"}
        fields[label] = matched.group(1).strip()
    if fields["情绪"] not in MOODS or fields["值不值得说"] not in {"说", "不说"}:
        return {"action": "protocol", "problem": "invalid_protocol"}
    if fields["值不值得说"] == "不说":
        return {"action": "silent", "mood": fields["情绪"], "text": ""}
    if len(re.sub(r"\s+", "", fields["台词"])) > 25:
        return {"action": "protocol", "problem": "line_too_long", "text": ""}
    result = parse_natural(fields["台词"])
    result["mood"] = fields["情绪"]
    return result


def parse_visual_protocol(raw: str) -> dict:
    matched = re.search(r"^\s*变化\s*[：:]\s*(.*)$", raw or "", re.M)
    if not matched or "没变" in matched.group(1):
        return {"action": "silent", "change": "", "text": ""}
    speech = re.search(r"^\s*台词\s*[：:]\s*(.*)$", raw or "", re.M)
    result = parse_natural(speech.group(1) if speech else "")
    result["change"] = matched.group(1)[:180]
    result["mood"] = _mood(raw)
    return result


def evaluate(raw: str, *, evidence: str, recent: list[str] | None = None, kind: str = "reaction") -> dict:
    parsed = parse_natural(raw)
    action = parsed["action"]
    spoken = parsed.get("text", "")
    problem = str(parsed.get("problem") or "")
    if spoken:
        from .conversation import strip_opening
        spoken = strip_opening(spoken)
        if kind != "company":
            from .media_director import unsupported_reply
            problem = unsupported_reply(evidence, spoken)
            if problem:
                action = "unsupported"
        if not problem:
            from .along import same_scene
            from .watch import hollow_company
            if _META.search(spoken):
                action, problem = "hollow", "陪伴套话不是有效互动"
            elif any(same_scene(spoken, old) for old in (recent or [])[-3:]):
                action, problem = "duplicate", "同一个点不重复说"
            elif kind != "company" and hollow_company(spoken):
                action, problem = "hollow", "没有接住当前内容"
    mood = _mood(spoken) if spoken else "平静"
    if action != "speak":
        spoken = ""
    return {"action": action, "text": spoken, "mood": mood, "change": "",
            "problem": problem, "performance": [{"type": "emo", "value": _EMO[mood]}] if action == "speak" else []}


def _prompt(messages: list[dict]) -> str:
    return "\n\n".join(str(message.get("content") or "") for message in messages if message.get("content"))


async def direct_reply(
    conf: dict,
    messages: list[dict],
    *,
    evidence: str,
    valid=lambda: True,
    recent: list[str] | None = None,
    stream=None,
    kind: str = "reaction",
) -> dict:
    from ...services.llm import stream_chat

    selected = generator()
    pieces: list[str] = []
    errors: list[str] = []
    raw = ""
    try:
        async with asyncio.timeout(31):
            if selected == "minicpm" and stream is None:
                from .service import eyes_react
                data = await asyncio.to_thread(eyes_react, _prompt(messages), 30)
                raw = str(data.get("text") or "")
                if not data.get("ok"):
                    errors.append("minicpm_error")
            else:
                generate = stream or stream_chat
                async with aclosing(generate(conf, messages)) as source:
                    async for event in source:
                        if not valid():
                            return {"action": "drop", "text": "", "attempts": [
                                {"raw": "".join(pieces), "errors": ["candidate_expired"], "problem": ""}
                            ], "performance": [], "generator": selected}
                        if event.get("type") == "text":
                            pieces.append(event.get("delta") or "")
                        elif event.get("type") == "error":
                            errors.append(str(event.get("code") or "error"))
                raw = "".join(pieces)
    except TimeoutError:
        errors.append("generation_timeout")
    result = evaluate(raw, evidence=evidence, recent=recent, kind=kind)
    action = result["action"]
    if not valid():
        action = "drop"
        errors.append("candidate_expired")
    if errors and not raw.strip():
        action = "protocol"
    elif errors and action == "speak":
        action = "silent"
    if action != "speak":
        result["text"] = ""
        result["performance"] = []
    result["action"] = action
    result["attempts"] = [{"raw": raw, "errors": errors, "problem": result["problem"]}]
    result["generator"] = selected
    return result
