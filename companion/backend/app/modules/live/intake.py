"""平台无关的接收边界；不选题、不调用模型，先去重再产生任何业务副作用。"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import replace

from .events import LiveEvent, SPEAKABLE, clip_event


class EventIntake:
    def __init__(self) -> None:
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self.counts: Counter = Counter()

    def accept(self, event: LiveEvent) -> LiveEvent | None:
        ev = clip_event(replace(event))
        if ev.kind not in SPEAKABLE | {"like"} or (ev.kind == "comment" and not ev.content):
            self.counts["invalid"] += 1
            return None
        if ev.msg_id:
            key = (ev.platform, ev.msg_id)
            if key in self._seen:
                self.counts["duplicate"] += 1
                return None
            self._seen[key] = None
            if len(self._seen) > 4000:
                self._seen.popitem(last=False)
        self.counts["accepted"] += 1
        return ev

    def public(self) -> dict:
        return dict(self.counts)
