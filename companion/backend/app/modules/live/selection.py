"""无模型的注意力策略：合并相同话题，优先可接的问题，兼顾等待与观众公平。"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from .events import LiveEvent


def topic_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).casefold())


def select_comments(events: list[LiveEvent], now: float, limit: int,
                    replied: dict[str, float]) -> list[LiveEvent]:
    groups: dict[str, list[LiveEvent]] = defaultdict(list)
    for ev in events:
        groups[topic_key(ev.content) or ev.kind].append(ev)

    def score(ev: LiveEvent) -> float:
        question = bool(re.search(r"[?？]|怎么|为什么|哪[个里]|什么|能不能|可以吗", ev.content))
        substantive = len(topic_key(ev.content)) >= 5
        repeated = min(len({e.user_key() for e in groups[topic_key(ev.content) or ev.kind]}) - 1, 4)
        fairness = 25 if now - replied.get(ev.user_key(), float("-inf")) < 45 else 0
        return question * 30 + substantive * 10 + repeated * 4 + min(max(now - ev.ts, 0), 30) - fairness

    ranked = sorted(events, key=score, reverse=True)
    picked: list[LiveEvent] = []
    topics: set[str] = set()
    users: set[str] = set()
    for ev in ranked:
        key = topic_key(ev.content) or ev.kind
        if key in topics or ev.user_key() in users:
            continue
        picked.append(ev)
        topics.add(key)
        users.add(ev.user_key())
        if len(picked) >= min(limit, 3):
            break
    return picked
