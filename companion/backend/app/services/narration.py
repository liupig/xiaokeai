"""括号内心 OS / 动作描写：不进 TTS，转成表演标记。"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

STAGE_RE = re.compile(r"[（(【]([^）)】]{1,48})[）)】]")

_INTENT_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (r"比心|心动|喜欢你", ("heart",)),
    (r"亲|吻|mua", ("kiss",)),
    (r"鞠躬|点头哈腰", ("bow",)),
    (r"坐下|坐下来", ("sit",)),
    (r"挥手|招手|打招呼", ("greet",)),
    (r"摇头|摆手|不是", ("shake",)),
    (r"点头|嗯了一下", ("nod",)),
    (r"想|托腮|撑着腮|沉吟", ("think",)),
    (r"脸红|害羞|不好意思|耳尖", ("shy",)),
    (r"坏笑|偷笑|眨眼|俏皮|调皮", ("tease",)),
    (r"歪|侧头|脑袋|偏头|头一歪", ("cute", "look")),
    (r"蹭|挨着|凑近|靠近|靠过来|钻进|掌心|怀里|贴过来", ("cute", "shy")),
    (r"笑|嘿嘿|咯咯", ("tease",)),
    (r"叹气|委屈|瘪嘴", ("comfort",)),
    (r"看你|盯|抬眼|垂眸|看过来", ("look",)),
)


def map_stage_inner(inner: str) -> List[Dict[str, str]]:
    t = (inner or "").strip()
    if not t:
        return []
    intents: List[str] = []
    emo = ""
    for pat, names in _INTENT_RULES:
        if re.search(pat, t, re.I):
            for n in names:
                if n not in intents:
                    intents.append(n)
            if re.search(r"蹭|掌心|怀里|亲|比心|笑|歪", t):
                emo = emo or "happy:0.7"
            if re.search(r"脸红|害羞", t):
                emo = "happy:0.55"
            if re.search(r"叹气|委屈", t):
                emo = "sad:0.55"
    if not intents:
        if re.search(r"其实|内心|心想|暗想", t):
            intents.append("think")
        else:
            intents.append("look")
    out: List[Dict[str, str]] = []
    if emo:
        out.append({"type": "emo", "value": emo})
    for name in intents[:3]:
        out.append({"type": "intent", "value": name})
    return out


def peel_stage_dirs(text: str) -> Tuple[str, List[Dict[str, str]]]:
    """去掉（动作）【动作】(laughs)，返回能说的正文 + 表演事件。"""
    events: List[Dict[str, str]] = []

    def repl(m: re.Match[str]) -> str:
        events.extend(map_stage_inner(m.group(1)))
        return ""

    spoken = STAGE_RE.sub(repl, text or "")
    spoken = re.sub(r"[ \t]{2,}", " ", spoken)
    spoken = re.sub(r"^[，,、；;]+", "", spoken).strip()
    return spoken, events
