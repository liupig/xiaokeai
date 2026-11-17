"""无模型的注意力策略：合并相同话题，优先可接的问题，兼顾等待与观众公平。"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from .events import LiveEvent, emote_only


def topic_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).casefold())


def select_comments(events: list[LiveEvent], now: float, limit: int,
                    replied: dict[str, float]) -> list[LiveEvent]:
    # 数字留给猜数字节目；孤立标点、0、纯表情不值得消耗一次口播。
    events = [ev for ev in events if ev.kind != "comment"
              or (len(topic_key(ev.content)) > 1 and not emote_only(ev.content))]
    if not events:
        return []
    groups: dict[str, list[LiveEvent]] = defaultdict(list)
    for ev in events:
        groups[topic_key(ev.content) or ev.kind].append(ev)

    def score(ev: LiveEvent) -> float:
        question = bool(re.search(r"[?？]|怎么|为什么|哪[个里]|什么|能不能|可以吗", ev.content))
        substantive = len(topic_key(ev.content)) >= 5
        low_information = len(topic_key(ev.content)) <= 1
        emote = emote_only(ev.content)
        repeated = min(len({e.user_key() for e in groups[topic_key(ev.content) or ev.kind]}) - 1, 4)
        fairness = 25 if now - replied.get(ev.user_key(), float("-inf")) < 45 else 0
        return (question * 30 + substantive * 10 + repeated * 4
                + min(max(now - ev.ts, 0), 30) - fairness - low_information * 20 - emote * 60)

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
