"""从一句人话里看出要开哪一个。认不出来就当普通聊天。"""
from __future__ import annotations

import re

from .titles import TITLES, norm

_BLOCK = (
    "塔罗", "酒馆", "魅影", "视觉", "记忆", "设置", "跳舞", "许愿",
    "音乐", "歌曲", "电影", "视频", "摄像头", "动捕",
    "tarot", "tavern", "dance", "settings", "vision",
)
_STRICT = re.compile(
    r"^(?:请|帮我|给我|我要|我想要|我想|来)?\s*(?:打开|启动|运行|玩|开)\s*(?:一下|一个|一局|下)?\s*[:：]?\s*(.+)$",
)
_EN = re.compile(
    r"^(?:please\s+)?(?:open|launch|start|play)\s+(?:the\s+)?(?:game\s+)?(.+)$",
    re.I,
)
_LOOSE = re.compile(r"打开|启动|我要玩|我想玩|想玩|来玩|帮我开|\bopen\b|\blaunch\b|\bplay\b", re.I)


def extract_query(text: str) -> str:
    raw = (text or "").strip().strip("。！!？?~～ ")
    if not raw:
        return ""
    query = ""
    matched = _STRICT.match(raw) or _EN.match(raw)
    if matched:
        query = matched.group(1).strip()
        query = re.split(r"[，,。！!？?\n]", query, maxsplit=1)[0].strip()
        query = re.sub(r"^(?:一下|一个|一局|这个|那个)\s*", "", query)
        query = re.sub(r"(?:吗|吧|了|啊|呀|呗|呢|哦)+$", "", query).strip()
        query = re.sub(r"\s+(?:please|now)$", "", query, flags=re.I).strip()
    elif _LOOSE.search(raw):
        folded = norm(raw)
        for title in TITLES:
            for name in sorted(title.names, key=len, reverse=True):
                token = norm(name)
                if len(token) >= 2 and token in folded:
                    query = name
                    break
            if query:
                break
    if not query or len(query) > 40:
        return ""
    if query in {"游戏", "一下", "一个"}:
        return ""
    low = query.lower()
    if any(word in query or word in low for word in _BLOCK):
        return ""
    return query
