"""把开放平台的 JSON 通知收成直播事件。"""
from __future__ import annotations

import json

from ..events import LiveEvent

_CMDS = {
    "LIVE_OPEN_PLATFORM_DM": "comment",
    "LIVE_OPEN_PLATFORM_SEND_GIFT": "gift",
    "LIVE_OPEN_PLATFORM_SUPER_CHAT": "superchat",
    "LIVE_OPEN_PLATFORM_GUARD": "guard",
    "LIVE_OPEN_PLATFORM_LIKE": "like",
}


def _name(data: dict) -> str:
    user = data.get("user_info") if isinstance(data.get("user_info"), dict) else {}
    return str(data.get("uname") or data.get("user_name") or user.get("uname") or "")


def _uid(data: dict) -> str:
    return str(data.get("open_id") or data.get("uid") or "")


def events_from_json(raw: bytes | str) -> list[LiveEvent]:
    try:
        obj = json.loads(raw or b"")
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return []
    if isinstance(obj, list):
        found: list[LiveEvent] = []
        for item in obj:
            if isinstance(item, dict):
                found.extend(events_from_obj(item))
        return found
    if isinstance(obj, dict):
        return events_from_obj(obj)
    return []


def events_from_obj(obj: dict) -> list[LiveEvent]:
    cmd = str(obj.get("cmd") or "")
    kind = _CMDS.get(cmd, "")
    data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
    if not kind:
        return []
    nickname = _name(data)
    uid = _uid(data)
    msg_id = str(data.get("msg_id") or data.get("message_id") or "")
    if kind == "comment":
        content = str(data.get("msg") or data.get("message") or "")
        return [LiveEvent("bilibili", "comment", nickname, content, uid=uid, msg_id=msg_id)]
    if kind == "gift":
        gift = str(data.get("gift_name") or "礼物")
        count = int(data.get("gift_num") or data.get("num") or 1)
        price = int(data.get("price") or 0)
        content = f"送出 {gift}×{count}"
        return [LiveEvent("bilibili", "gift", nickname, content, uid=uid, gift=gift,
                          count=count, price=price, msg_id=msg_id)]
    if kind == "superchat":
        content = str(data.get("message") or data.get("message_jpn") or "")
        return [LiveEvent("bilibili", "superchat", nickname, content or "醒目留言",
                          uid=uid, msg_id=msg_id, price=int(float(data.get("rmb") or 0) * 100))]
    if kind == "guard":
        return [LiveEvent("bilibili", "guard", nickname, "上舰", uid=uid, msg_id=msg_id, gift="上舰")]
    count = int(data.get("like_count") or data.get("count") or 1)
    return [LiveEvent("bilibili", "like", nickname, f"点赞×{count}", uid=uid, count=count, msg_id=msg_id)]
