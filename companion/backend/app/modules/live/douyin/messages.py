"""把一帧直播推送收成弹幕、礼物、点赞。进场和人数统计不收。"""
from __future__ import annotations

import base64
import gzip
import json
import time
from typing import Any

from .wire import blob, fields, num, put_field_bytes, put_field_str, put_field_varint, text

_KEEP = {
    "WebcastChatMessage": "comment",
    "WebcastEmojiChatMessage": "comment",
    "WebcastGiftMessage": "gift",
    "WebcastLikeMessage": "like",
    "WebcastSocialMessage": "follow",
    "WebcastControlMessage": "control",
}


def event(kind: str, msg_id: Any, nickname: str, content: str, *,
          source: str, gift: str = "", count: int = 0) -> dict:
    return {
        "kind": kind,
        "msg_id": str(msg_id or ""),
        "nickname": (nickname or "").strip(),
        "content": (content or "").strip(),
        "gift": gift or "",
        "count": int(count or 0),
        "source": source,
        "ts": int(time.time() * 1000),
    }


def _user_name(payload_fields: dict, field_no: int) -> str:
    raw = blob(payload_fields.get(field_no))
    if not raw:
        return ""
    return text(fields(raw).get(3))


def from_method(method: str, payload: bytes, msg_id: Any, source: str) -> dict | None:
    kind = _KEEP.get(method or "")
    if not kind or not payload:
        return None
    body = fields(payload)
    if kind == "comment" and method == "WebcastEmojiChatMessage":
        nick = _user_name(body, 2)
        content = text(body.get(5)) or "［表情］"
        return event("comment", msg_id, nick, content, source=source)
    if kind == "comment":
        return event("comment", msg_id, _user_name(body, 2), text(body.get(3)), source=source)
    if kind == "gift":
        gift = fields(blob(body.get(15)))
        name = text(gift.get(16)) or "礼物"
        count = num(body.get(6)) or num(body.get(5)) or num(body.get(29)) or 1
        return event("gift", msg_id, _user_name(body, 7), f"送出 {name}×{count}",
                     source=source, gift=name, count=count)
    if kind == "like":
        count = num(body.get(2)) or 1
        return event("like", msg_id, _user_name(body, 5), f"点赞×{count}",
                     source=source, count=count)
    if kind == "follow":
        return event("follow", msg_id, _user_name(body, 2), "关注了", source=source)
    if num(body.get(2)) == 3:
        return event("control", msg_id, "", "ended", source=source)
    return None


def _one(blob_bytes: bytes, source: str) -> dict | None:
    msg = fields(blob_bytes)
    method = text(msg.get(1))
    payload = blob(msg.get(2))
    return from_method(method, payload, num(msg.get(3)), source)


def events_from_response(buf: bytes, source: str = "room") -> tuple[list[dict], str, str, bool]:
    """Response 消息体。返回事件、cursor、internal_ext、要不要 ack。"""
    body = fields(buf)
    found = []
    for item in body.get(1, []):
        if not isinstance(item, bytes):
            continue
        ev = _one(item, source)
        if ev and (ev["kind"] == "control" or ev["content"] or ev["nickname"]):
            if ev["kind"] == "comment" and not ev["content"]:
                continue
            found.append(ev)
    return found, text(body.get(2)), text(body.get(5)), bool(num(body.get(9)))


def ack_frame(log_id: int, internal_ext: str) -> bytes:
    return (
        put_field_varint(2, int(log_id or 0))
        + put_field_str(7, "ack")
        + put_field_bytes(8, (internal_ext or "").encode("utf-8"))
    )


def heartbeat_frame() -> bytes:
    return put_field_str(7, "hb")


def unpack_push(raw: bytes) -> tuple[list[dict], bytes | None]:
    """网页 websocket 的一帧：PushFrame 里包着 gzip 的 Response。"""
    frame = fields(raw)
    payload = blob(frame.get(8))
    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    events, _cursor, internal, need_ack = events_from_response(payload)
    ack = ack_frame(num(frame.get(2)), internal) if need_ack else None
    return events, ack


def events_from_body(content: bytes) -> tuple[list[dict], str, str]:
    """im/fetch 的响应。可能是 JSON，也可能是 protobuf / gzip。"""
    data = content or b""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if not data:
        return [], "", ""
    if data[:1] in (b"{", b"["):
        return _from_json(data)
    if data[:1] == b"<" or data[:9].lower().startswith(b"<!doctype"):
        raise RuntimeError("直播间没有把弹幕交出来")
    try:
        parsed = fields(data)
    except ValueError as exc:
        raise RuntimeError("认不出这一包弹幕") from exc
    blobs = [item for item in parsed.get(1, []) if isinstance(item, bytes)]
    if blobs and text(fields(blobs[0]).get(1)).startswith("Webcast"):
        events, cursor, internal, _need = events_from_response(data)
        return events, cursor, internal
    if blob(parsed.get(8)):
        events, _ack = unpack_push(data)
        return events, "", ""
    if not parsed:
        raise RuntimeError("认不出这一包弹幕")
    return [], "", ""


def _from_json(data: bytes) -> tuple[list[dict], str, str]:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("弹幕接口返回的不是 JSON") from exc
    status = parsed.get("status_code")
    if status not in (0, None, "0"):
        msg = parsed.get("status_msg") or parsed.get("message") or f"弹幕接口拒绝了（{status}）"
        raise RuntimeError(str(msg))
    node = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
    cursor = str(node.get("cursor") or "")
    internal = str(node.get("internal_ext") or node.get("internalExt") or "")
    found = []
    for item in node.get("messages") or []:
        if not isinstance(item, dict):
            continue
        method = str(item.get("method") or "")
        payload = item.get("payload")
        raw = b""
        if isinstance(payload, str) and payload:
            try:
                raw = base64.b64decode(payload)
            except Exception:
                raw = b""
        elif isinstance(payload, dict):
            raw = b""
        ev = from_method(method, raw, item.get("msg_id") or item.get("msgId"), "room") if raw else None
        if ev is None and method == "WebcastChatMessage":
            content = str(item.get("content") or "")
            nick = str(item.get("nickname") or item.get("nick_name") or "")
            ev = event("comment", item.get("msg_id"), nick, content, source="room")
        if ev and (ev["kind"] == "control" or ev["content"]):
            found.append(ev)
    return found, cursor, internal
