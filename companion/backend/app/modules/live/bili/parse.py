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
    # 直播姬/OBS 场景使用网页信息流，字段与开放平台不同。
    if cmd == "DANMU_MSG":
        info = obj.get("info") if isinstance(obj.get("info"), list) else []
        user = info[2] if len(info) > 2 and isinstance(info[2], list) else []
        extra = {}
        if info and isinstance(info[0], list) and len(info[0]) > 15 and isinstance(info[0][15], dict):
            raw_extra = info[0][15].get("extra")
            if isinstance(raw_extra, str):
                try:
                    extra = json.loads(raw_extra)
                except json.JSONDecodeError:
                    extra = {}
        content = str(info[1] if len(info) > 1 else "")
        nickname = str(user[1] if len(user) > 1 else "")
        uid = str(user[0] if user else "")
        msg_id = str(obj.get("msg_id") or extra.get("id_str") or "")
        ts = float(obj.get("send_time") or 0) / 1000 if obj.get("send_time") else 0
        kwargs = {"ts": ts} if ts else {}
        return [LiveEvent("bilibili", "comment", nickname, content, uid=uid, msg_id=msg_id, **kwargs)]
    if cmd in {"SEND_GIFT", "SUPER_CHAT_MESSAGE", "GUARD_BUY", "LIKE_INFO_V3_CLICK"}:
        data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
        user = data.get("user_info") if isinstance(data.get("user_info"), dict) else {}
        nickname = str(data.get("uname") or data.get("username") or user.get("uname") or "")
        uid = str(data.get("uid") or user.get("uid") or "")
        msg_id = str(data.get("msg_id") or data.get("id") or obj.get("msg_id") or "")
        if cmd == "SEND_GIFT":
            gift = str(data.get("giftName") or data.get("gift_name") or "礼物")
            count = int(data.get("num") or data.get("gift_num") or 1)
            return [LiveEvent("bilibili", "gift", nickname, f"送出 {gift}×{count}", uid=uid,
                              gift=gift, count=count, price=int(data.get("price") or 0), msg_id=msg_id)]
        if cmd == "SUPER_CHAT_MESSAGE":
            content = str(data.get("message") or "醒目留言")
            return [LiveEvent("bilibili", "superchat", nickname, content, uid=uid,
                              msg_id=msg_id, price=int(float(data.get("price") or 0) * 1000))]
        if cmd == "GUARD_BUY":
            gift = str(data.get("gift_name") or "上舰")
            return [LiveEvent("bilibili", "guard", nickname, gift, uid=uid,
                              msg_id=msg_id, gift=gift, count=int(data.get("num") or 1),
                              price=int(data.get("price") or 0))]
        return [LiveEvent("bilibili", "like", nickname, "点赞", uid=uid, count=1, msg_id=msg_id)]
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
