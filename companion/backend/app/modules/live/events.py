"""直播间事件。平台字段不同，进队列之前收成同一种。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

SPEAKABLE = frozenset({"comment", "gift", "superchat", "guard", "follow"})
PRIORITY_KINDS = frozenset({"gift", "superchat", "guard"})


@dataclass
class LiveEvent:
    platform: str
    kind: str
    nickname: str
    content: str
    uid: str = ""
    gift: str = ""
    count: int = 0
    price: int = 0
    msg_id: str = ""
    ts: float = field(default_factory=time.time)
    seq: int = 0

    def user_key(self) -> str:
        who = (self.uid or self.nickname or "").strip() or "anon"
        return f"{self.platform}:{who}"

    def priority(self) -> int:
        if self.kind == "superchat":
            return 100
        if self.kind == "guard":
            return 90
        if self.kind == "gift":
            yuan = max(int(self.price or 0), 0) // 1000
            return 80 + min(int(self.count or 1), 20) + min(yuan, 15)
        if self.kind == "follow":
            return 40
        if self.kind == "comment":
            return 20
        return 1

    def public(self) -> dict:
        return {
            "seq": self.seq,
            "platform": self.platform,
            "kind": self.kind,
            "nickname": self.nickname,
            "content": self.content,
            "gift": self.gift,
            "count": self.count,
            "ts": int(self.ts * 1000),
        }


def clip_event(ev: LiveEvent) -> LiveEvent:
    ev.nickname = (ev.nickname or "").strip()[:24] or "有人"
    ev.content = (ev.content or "").strip()[:80]
    ev.gift = (ev.gift or "").strip()[:24]
    ev.uid = (ev.uid or "").strip()[:64]
    ev.msg_id = (ev.msg_id or "").strip()[:80]
    ev.platform = (ev.platform or "").strip()[:16] or "live"
    ev.kind = (ev.kind or "").strip()[:16]
    try:
        ev.count = max(0, int(ev.count or 0))
    except (TypeError, ValueError):
        ev.count = 0
    try:
        ev.price = max(0, int(ev.price or 0))
    except (TypeError, ValueError):
        ev.price = 0
    return ev
