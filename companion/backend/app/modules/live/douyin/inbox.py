"""弹幕收件箱。网页直播间和开放平台回调进同一条队列。"""
from __future__ import annotations

import json
import threading
from collections import deque
from typing import Any

from .messages import event

_LOCK = threading.Lock()
_ITEMS: deque[dict] = deque(maxlen=200)
_SEEN: deque[str] = deque(maxlen=4000)
_SEEN_SET: set[str] = set()
_SEQ = 0


def clear() -> None:
    global _SEQ
    with _LOCK:
        _ITEMS.clear()
        _SEEN.clear()
        _SEEN_SET.clear()
        _SEQ = 0


def snapshot_seq() -> int:
    with _LOCK:
        return _SEQ


def since(seq: int) -> list[dict]:
    with _LOCK:
        return [dict(item) for item in _ITEMS if int(item.get("seq") or 0) > int(seq or 0)]


def add_many(rows: list[dict]) -> int:
    added = 0
    for row in rows:
        if add(row):
            added += 1
    return added


def add(row: dict) -> bool:
    global _SEQ
    if not row:
        return False
    if row.get("kind") == "comment" and not (row.get("content") or "").strip():
        return False
    key = (row.get("msg_id") or "").strip()
    if not key:
        key = "|".join([
            str(row.get("source") or ""),
            str(row.get("kind") or ""),
            str(row.get("nickname") or ""),
            str(row.get("content") or ""),
            str(int(row.get("ts") or 0) // 1000),
        ])
    with _LOCK:
        if key in _SEEN_SET:
            return False
        if len(_SEEN) == _SEEN.maxlen:
            old = _SEEN.popleft()
            _SEEN_SET.discard(old)
        _SEEN.append(key)
        _SEEN_SET.add(key)
        global_seq = _SEQ + 1
        _SEQ = global_seq
        item = dict(row)
        item["seq"] = global_seq
        item["msg_id"] = key
        _ITEMS.append(item)
    return True


def accept_callback(msg_type: str, body: str, room_id: str = "") -> int:
    """开放平台 POST 的 JSON。评论、礼物、点赞进收件箱。"""
    try:
        parsed = json.loads(body or "[]")
    except json.JSONDecodeError:
        return 0
    rows: list[Any]
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        inner = parsed.get("data")
        rows = inner if isinstance(inner, list) else [parsed]
    else:
        return 0
    kind = {
        "live_comment": "comment",
        "live_gift": "gift",
        "live_like": "like",
        "live_fansclub": "follow",
    }.get((msg_type or "").strip(), "")
    if not kind:
        return 0
    found = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        nick = str(row.get("nickname") or "")
        content = str(row.get("content") or "")
        count = int(row.get("gift_num") or row.get("like_num") or row.get("count") or 0)
        gift = str(row.get("gift_name") or row.get("sec_gift_id") or "")
        if kind == "gift" and not content:
            content = f"送出 {gift or '礼物'}×{count or 1}"
        elif kind == "like" and not content:
            content = f"点赞×{count or 1}"
        elif kind == "follow" and not content:
            content = "粉丝团"
        ev = event(kind, row.get("msg_id"), nick, content, source="callback", gift=gift, count=count)
        if room_id:
            ev["room_id"] = room_id
        found.append(ev)
    return add_many(found)
