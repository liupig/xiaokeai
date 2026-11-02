"""弹幕队列。礼物和醒目留言立刻可取，普通弹幕按窗口聚合，同一个人冷却。"""
from __future__ import annotations

import re
import time
from collections import deque

from .commands import match_act, match_song
from .config import batch_window, feature_on, song_titles, user_cooldown
from .events import PRIORITY_KINDS, SPEAKABLE, LiveEvent, clip_event
from .selection import select_comments, topic_key

_GUESS = re.compile(r"^\s*(\d{1,2})\s*$")
_MAX = 400
_SEEN = 4000


class LiveQueue:
    def __init__(self) -> None:
        self._items: deque[LiveEvent] = deque()
        self._user_at: dict[str, float] = {}
        self._seen: deque[str] = deque()
        self._seen_set: set[str] = set()
        self._replied: dict[str, float] = {}
        self._topic_at: dict[str, float] = {}
        self.expired = 0
        self.dropped = 0

    def clear(self) -> None:
        self._items.clear()
        self._user_at.clear()
        self._seen.clear()
        self._seen_set.clear()
        self._replied.clear()
        self._topic_at.clear()

    def prune(self, now: float) -> None:
        # 过时的闲聊不要排到几分钟后再念；付费事件保留更长的服务窗口。
        keep = deque(item for item in self._items
                     if now - item.ts <= (300 if item.kind in PRIORITY_KINDS else 45))
        self.expired += len(self._items) - len(keep)
        self._items = keep
        self._replied = {key: at for key, at in self._replied.items() if now - at < 120}
        self._user_at = {key: at for key, at in self._user_at.items() if now - at < 120}
        self._topic_at = {key: at for key, at in self._topic_at.items() if now - at < 12}

    def __len__(self) -> int:
        return len(self._items)

    def offer(self, ev: LiveEvent, now: float | None = None, cfg: dict | None = None) -> bool:
        now = time.time() if now is None else now
        cfg = cfg or {}
        ev = clip_event(ev)
        if ev.kind not in SPEAKABLE:
            return False
        if ev.kind == "comment" and not ev.content:
            return False
        if ev.msg_id:
            key = f"{ev.platform}:{ev.msg_id}"
            if key in self._seen_set:
                return False
            if len(self._seen) >= _SEEN:
                old = self._seen.popleft()
                self._seen_set.discard(old)
            self._seen.append(key)
            self._seen_set.add(key)
        if ev.kind == "comment":
            if now - self._topic_at.get(topic_key(ev.content), float("-inf")) < 12:
                return False
            wait = user_cooldown(cfg)
            last = self._user_at.get(ev.user_key(), 0)
            if wait and now - last < wait:
                return False
            self._user_at[ev.user_key()] = now
            self._items = deque(item for item in self._items
                                if not (item.kind == "comment" and item.user_key() == ev.user_key()))
        self._items.append(ev)
        self._trim()
        return True

    def _trim(self) -> None:
        if len(self._items) <= _MAX:
            return
        comments = [item for item in self._items if item.kind == "comment"]
        keep = [item for item in self._items if item.kind != "comment"]
        keep = keep[-_MAX:]
        room = max(0, _MAX - len(keep))
        retained = [*keep, *(comments[-room:] if room else [])]
        self.dropped += len(self._items) - len(retained)
        self._items = deque(retained)

    def take_priority(self, cfg: dict, limit: int = 3) -> list[LiveEvent]:
        if not feature_on(cfg, "gifts"):
            return []
        picked = sorted((item for item in self._items if item.kind in PRIORITY_KINDS),
                        key=lambda item: item.priority(), reverse=True)[:limit]
        if not picked:
            return []
        drop = set(map(id, picked))
        self._items = deque(item for item in self._items if id(item) not in drop)
        picked.sort(key=lambda item: item.priority(), reverse=True)
        return picked

    def has_priority(self, cfg: dict) -> bool:
        if not feature_on(cfg, "gifts"):
            return False
        return any(item.kind in PRIORITY_KINDS for item in self._items)

    def take_act(self, cfg: dict) -> tuple[LiveEvent, str] | None:
        if not feature_on(cfg, "commands"):
            return None
        for item in list(self._items):
            if item.kind != "comment":
                continue
            act = match_act(item.content)
            if not act:
                continue
            self._items = deque(other for other in self._items if other is not item)
            return item, act
        return None

    def take_song(self, cfg: dict) -> tuple[LiveEvent, str] | None:
        titles = song_titles(cfg)
        if not titles:
            return None
        for item in list(self._items):
            if item.kind != "comment":
                continue
            title = match_song(item.content, titles)
            if not title:
                continue
            self._items = deque(other for other in self._items if other is not item)
            return item, title
        return None

    def take_guess(self) -> tuple[LiveEvent, int] | None:
        for item in list(self._items):
            if item.kind != "comment":
                continue
            matched = _GUESS.match(item.content or "")
            if not matched:
                continue
            number = int(matched.group(1))
            if number < 1 or number > 10:
                continue
            self._items = deque(other for other in self._items if other is not item)
            return item, number
        return None

    def take_batch(self, now: float, cfg: dict) -> list[LiveEvent] | None:
        if not feature_on(cfg, "reply"):
            return None
        comments = [item for item in self._items if item.kind in ("comment", "follow")]
        if not comments:
            return None
        size = int(cfg["pace"]["batch_size"])
        window = batch_window(cfg)
        oldest = min(item.ts for item in comments)
        if len(comments) < size and now - oldest < window:
            return None
        picked = select_comments(comments, now, size, self._replied)
        topics = {topic_key(item.content) for item in picked if item.kind == "comment"}
        drop = set(map(id, picked))
        self._items = deque(item for item in self._items if id(item) not in drop
                            and not (item.kind == "comment" and topic_key(item.content) in topics))
        for item in picked:
            self._replied[item.user_key()] = now
            if item.kind == "comment":
                self._topic_at[topic_key(item.content)] = now
        return picked
