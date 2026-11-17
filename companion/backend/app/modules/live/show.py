"""冷场、猜数字、许愿。都不靠外网。"""
from __future__ import annotations

import random
import re

from .events import LiveEvent

TOPICS = (
    "你们今天有没有哪件小事，是本来没期待，结果还挺开心的？",
    "如果今天只能保留一个瞬间，你会留哪一个？",
    "最近有没有一首歌，前奏一响你就知道是它？",
    "今天吃过最满意的一口是什么？没吃也可以说说想吃的。",
    "最近有什么小事，你嘴上嫌麻烦，其实心里还挺在意的？",
    "如果今晚能少做一件事，你最想把什么从清单里划掉？",
    "你们最近有没有遇到什么，离谱但又能当笑话讲的事？",
    "如果现在能暂停十分钟，你想坐着发呆，还是去做点什么？",
)

_WISH = re.compile(r"许愿[:：\s]*(.{2,40})")


class TopicDeck:
    def __init__(self) -> None:
        self._recent: list[str] = []

    def next(self) -> str:
        pool = [line for line in TOPICS if line not in self._recent]
        if not pool:
            pool = list(TOPICS)
        line = random.choice(pool)
        self._recent.append(line)
        self._recent = self._recent[-5:]
        return line


class GuessGame:
    def __init__(self) -> None:
        self.index = -1
        self.secret = 0
        self.open = False

    def should_announce(self, index: int) -> bool:
        return self.index != index

    def announce(self, index: int) -> str:
        self.index = index
        self.secret = random.randint(1, 10)
        self.open = True
        return "我们玩个小的。我心里有一个 1 到 10 的整数，弹幕猜。猜中我认。"

    def answer(self, nickname: str, number: int) -> str | None:
        if not self.open:
            return None
        who = nickname or "有人"
        if number == self.secret:
            self.open = False
            return f"{who}猜的 {number}，中了。"
        if number < self.secret:
            return f"{who}的 {number} 小了。"
        return f"{who}的 {number} 大了。"


class WishPool:
    def __init__(self) -> None:
        self._items: list[dict] = []

    def clear(self) -> None:
        self._items.clear()

    def note(self, ev: LiveEvent) -> None:
        if ev.kind != "comment":
            return
        matched = _WISH.search(ev.content or "")
        if not matched:
            return
        text = matched.group(1).strip()
        if not text:
            return
        self._items.append({"name": ev.nickname, "text": text, "done": False})
        if len(self._items) > 30:
            self._items = self._items[-30:]

    def pending(self) -> int:
        return sum(1 for item in self._items if not item["done"])

    def pop(self) -> dict | None:
        for item in self._items:
            if not item["done"]:
                item["done"] = True
                return item
        return None
