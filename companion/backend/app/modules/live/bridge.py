"""平台收件箱进主持队列。"""
from __future__ import annotations

from .events import LiveEvent
from .host import host


def from_inbox(item: dict) -> None:
    kind = str(item.get("kind") or "")
    if kind == "control":
        host.health.note("抖音直播间结束")
        return
    if kind not in ("comment", "gift", "like", "follow"):
        return
    try:
        count = int(item.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    try:
        price = int(item.get("price") or 0)
    except (TypeError, ValueError):
        price = 0
    host.ingest(LiveEvent(
        platform="douyin",
        kind=kind,
        nickname=str(item.get("nickname") or ""),
        content=str(item.get("content") or ""),
        gift=str(item.get("gift") or ""),
        count=count,
        price=price,
        msg_id=str(item.get("msg_id") or ""),
    ))
