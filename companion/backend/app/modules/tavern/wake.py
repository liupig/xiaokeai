"""聊天里点名魅影酒馆。牌桌由前端打开，这里只让她邀人入座。"""
from __future__ import annotations

import re

from ...locale_pack import compile_intent

_FOLD = re.compile(r"[\s。！？、,.!?;；…~～「」『』“”\"']+")


def _folded(text: str) -> str:
    return _FOLD.sub("", text or "")


def wants_tavern(text: str) -> bool:
    raw = text or ""
    folded = _folded(raw)
    close = compile_intent(None, "tavern.close")
    if close.search(raw) or close.search(folded):
        return False
    opener = compile_intent(None, "tavern.open")
    return bool(opener.search(raw) or opener.search(folded))


def invite_hint(text: str) -> str:
    if not wants_tavern(text):
        return ""
    return (
        "【魅影酒馆】牌桌已经打开，人还在门口。"
        "用一两句口语邀对方选牌组再入座。"
        "不要念规则，不要说打不开，不要自己宣布已经发牌。"
    )
