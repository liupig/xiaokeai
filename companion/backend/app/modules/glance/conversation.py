"""Opening and control protocol shared by user turns and continuous watching."""
from __future__ import annotations

import json
import re


def fast_request(text: str) -> str:
    """Only shortcut unambiguous requests; mixed actions still use the agent."""
    from .service import glance_from_user

    if re.search(r"不要|不用|不想|别|假如|如果|要是|开一局|开游戏|启动|来把|来一局|帮我开|跳舞", text or ""):
        return ""
    return glance_from_user(text)


def opening(ask: str, *, active: bool = False, lang: str = "zh-CN") -> str:
    from .service import parse_glance

    _, continuous = parse_glance(ask)
    continuous = continuous or ask.strip() == "开启"
    if lang.startswith("zh"):
        return ("好，我们接着看。" if active else "好呀，我陪你一起看。") if continuous else "好，我看一眼。"
    lines = {
        "ja": ("うん、一緒に見よう。", "ちょっと見てみるね。"),
        "ko": ("좋아, 같이 보자.", "잠깐 볼게."),
    }
    pair = lines.get(lang.split("-")[0], ("Sure, let's watch together.", "Let me take a look."))
    return pair[0 if continuous else 1]


def followup(lead: str, *, continuous: bool) -> str:
    return (
        f"你刚刚已经对他说了「{lead}」。这是同一轮的后半句，直接自然接上，不要再次答应、寒暄，"
        "不要再说我看看、你看看这个、我看到了。根据【眼前】回应他原来的要求，"
        "接一个具体细节，说自己的反应或问一个与眼前有关的小问题，不机械复述整幅画面。"
        + ("这是持续陪看的第一眼，之后会继续跟随当前陪看任务，不要说看完了。" if continuous else "这是一次查看，按他的问题给出结果。")
    )


def strip_opening(text: str, lead: str = "") -> str:
    """Remove repeated acknowledgements only at the beginning of the result."""
    spoken = (text or "").strip()
    if lead and spoken.startswith(lead):
        spoken = spoken[len(lead):].lstrip()
    return re.sub(r"^(?:(?:我看看|我看一眼|好[呀的啊]?[,，]?我看看)[。！!，,\s]*)+", "", spoken).strip()


def parse_control(value: str) -> dict[str, str]:
    """The agent may interpret nuanced requests into a bounded session update."""
    from .situation import read_steer

    raw = (value or "").strip()
    if not raw.startswith("{"):
        focus, talk = read_steer(raw)
        return {key: val for key, val in (("focus", focus), ("talk", talk)) if val is not None}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict) or set(data) - {"task", "focus", "talk"}:
        return {}
    if any(not isinstance(v, str) for v in data.values()):
        return {}
    if "talk" in data and data["talk"] not in {"more", "normal", "quiet"}:
        return {}
    return {key: val.strip()[:120] for key, val in data.items()}
