"""向旁边的眼睛进程要一句观察。模型不在这个进程里。"""
from __future__ import annotations

import os
import re

import httpx

_ALONG = ("看剧", "追剧", "陪我看", "陪看", "一起看", "看视频", "看片子", "看直播")


def eyes_url() -> str:
    return (os.environ.get("XIAOKE_EYES_URL") or "http://127.0.0.1:8766").rstrip("/")


def glance_from_user(text: str) -> str:
    """对方这句话就是在让她看屏幕。模型没写出标记时，宿主仍去看。"""
    raw = (text or "").strip()
    compact = re.sub(r"\s+", "", raw)
    if not compact or len(compact) > 40:
        return ""
    if any(word in compact for word in ("陪我看", "一起看", "看剧", "追剧", "看视频")):
        return "陪看 " + raw
    if any(word in compact for word in ("在哪", "在哪里", "哪儿")) and any(
        word in compact for word in ("看看", "看一下", "帮我看", "找")
    ):
        return "找 " + raw
    if any(word in compact for word in ("在干嘛", "在干吗", "在干什么", "在做什么", "干啥", "干什么", "看看我", "看一下我", "看我在", "帮我看")):
        return "在干嘛"
    return ""


def parse_glance(value: str) -> tuple[str, bool]:
    """技能写来的要求。陪看走这几秒，找东西和在干嘛走一帧。"""
    raw = (value or "").strip()
    compact = re.sub(r"\s+", "", raw)
    if compact.startswith("陪看"):
        rest = raw[2:].strip(" ：:，,")
        return rest or "陪我看现在正在播的内容", True
    if compact.startswith("找"):
        return raw[1:].strip(" ：:，,"), False
    if any(word in compact for word in _ALONG):
        return raw, True
    if compact in {"", "在干嘛", "我在干嘛", "我现在在干嘛", "干什么"}:
        return "", False
    return raw, False


def eyes_glance(
    ask: str = "",
    along: bool = False,
    timeout: float = 180,
    before: str = "",
    gate: bool = False,
) -> dict:
    try:
        resp = httpx.post(
            f"{eyes_url()}/api/glance",
            json={"monitor": 1, "ask": ask, "along": along, "before": before, "gate": gate},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {"ok": False, "text": "", "message": str(exc)}
    if not isinstance(data, dict):
        return {"ok": False, "text": "", "message": "眼睛没有返回"}
    return data


def _lead(ask: str, along: bool) -> str:
    base = (
        "铺垫已经说了：我看看。不要重复。不要再写 [glance:]。不要说技能。"
        "不要去点他的电脑，也不要说已经打开、已经找到了鼠标。"
        "【眼前】是你看见的，不是台词。不要复述，不要当旁白，不要介绍画面。"
    )
    if along:
        return base + (
            "你在陪他。【眼前】是接着上次的短叙事。只把这一眼新的重点用你自己的话说出来，不要把叙事念出来。"
            "没有新的重点就别硬聊。没有的不要编。\n"
        )
    if ask:
        return base + "按他要找的那件事说，在画面的哪一块。没看见就说没看见，不要编。\n"
    return base + "他问你在干嘛。用「事」跟他说话，像你本来就坐在旁边。没有的不要编。\n"


def _spoken(content: str) -> str:
    text = re.sub(r"\[[a-z]+(?::[^\]]*)?\]", "", content or "", flags=re.I)
    return " ".join(text.split())[:80]


def beside_cue(seen: str, prior: list | None = None, trail: list[str] | None = None) -> str:
    """陪看时把画面经过和刚说过的话一起给她，让这一句接得上。"""
    lines = [
        "对方没说话。你在陪他。用【现场】里的那个人说话。",
        "接下面已经说过的话，不要另起一个话题。",
        "【眼前】是接着上次的短叙事，不是台词。不要把叙事念出来。",
        "只把这一眼新的重点用你自己的话说给他，接上【刚说过】。",
        "不要说技能，不要写 [glance:]。不要去点他的电脑。",
    ]
    talked: list[str] = []
    for message in prior or []:
        role = (message.get("role") or "").strip()
        content = _spoken(message.get("content") or "")
        if role not in {"user", "assistant"} or not content:
            continue
        who = "她" if role == "assistant" else "对方"
        talked.append(f"{who}：{content}")
    if talked:
        lines.append("【刚说过】\n" + "\n".join(talked[-8:]))
    older = [line for line in (trail or []) if line.strip() and line.strip() != (seen or "").strip()]
    if older:
        lines.append("【画面经过】\n" + "\n".join(f"{i + 1}. {line}" for i, line in enumerate(older[-6:])))
    lines.append("【眼前】" + seen)
    return "\n".join(lines)


def glance_note(data: dict | None = None, ask: str = "") -> str:
    """放进【现场】的【眼前】。眼睛没开、画面是黑的，也写成一句，让她照实说。"""
    question, along = parse_glance(ask)
    found = eyes_glance(question, along) if data is None else data
    text = str(found.get("text") or "").strip()
    lead = _lead(question, along)
    if not found.get("ok") or not text:
        reason = str(found.get("message") or "").strip() or "没有看清"
        return lead + "【眼前】这一眼没看成。" + reason
    return lead + "【来源】这一眼来自屏幕。屏幕上的人物和情节不是他。\n【眼前】" + text
