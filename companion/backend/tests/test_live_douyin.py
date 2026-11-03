"""抖音弹幕：房间号、推送帧、收件箱、开放平台回调。不连真直播间。"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.flags import MODULE_KEYS, _DEFAULT_OFF  # noqa: E402
from app.modules.live.douyin import inbox  # noqa: E402
from app.modules.live.douyin.messages import events_from_body, unpack_push  # noqa: E402
from app.modules.live.douyin.room import room_id_from_html, web_rid  # noqa: E402
from app.modules.live.douyin.sign import callback_signature, signature_ok  # noqa: E402
from app.modules.live.douyin.wire import put_field_bytes, put_field_str, put_field_varint  # noqa: E402


def _chat_frame() -> bytes:
    user = put_field_str(3, "小周")
    chat = put_field_bytes(2, user) + put_field_str(3, "晚上好")
    message = put_field_str(1, "WebcastChatMessage") + put_field_bytes(2, chat) + put_field_varint(3, 99)
    response = put_field_bytes(1, message) + put_field_str(2, "cur-1") + put_field_str(5, "ext") + put_field_varint(9, 1)
    return put_field_varint(2, 7) + put_field_bytes(8, gzip.compress(response))


def test_live_douyin_is_a_module_and_defaults_off():
    assert "live_douyin" in MODULE_KEYS
    assert "live_douyin" in _DEFAULT_OFF


def test_room_link_and_page_yield_ids():
    assert web_rid("https://live.douyin.com/261378947940?from=web") == "261378947940"
    assert web_rid("261378947940") == "261378947940"
    assert web_rid("不是链接") == ""
    html = r'{"roomId\":\"7123456789012\"}'
    assert room_id_from_html(html) == "7123456789012"


def test_push_frame_is_a_comment_and_wants_an_ack():
    events, ack = unpack_push(_chat_frame())
    assert events[0]["nickname"] == "小周"
    assert events[0]["content"] == "晚上好"
    assert events[0]["kind"] == "comment"
    assert ack


def test_fetch_body_reads_a_response_and_rejects_html():
    user = put_field_str(3, "甲")
    gift_struct = put_field_str(16, "小心心")
    gift = put_field_varint(6, 2) + put_field_bytes(7, user) + put_field_bytes(15, gift_struct)
    message = put_field_str(1, "WebcastGiftMessage") + put_field_bytes(2, gift) + put_field_varint(3, 3)
    response = put_field_bytes(1, message) + put_field_str(2, "c")
    events, cursor, _internal = events_from_body(response)
    assert cursor == "c"
    assert events[0]["gift"] == "小心心"
    assert events[0]["content"] == "送出 小心心×2"
    try:
        events_from_body(b"<html>no</html>")
    except RuntimeError as exc:
        assert "没有把弹幕" in str(exc)
    else:
        raise AssertionError("html should not parse")


def test_inbox_keeps_a_comment_once_and_callback_uses_msg_id():
    inbox.clear()
    body = json.dumps([{"msg_id": "m1", "nickname": "甲", "content": "在吗"}])
    assert inbox.accept_callback("live_comment", body, "9") == 1
    assert inbox.accept_callback("live_comment", body, "9") == 0
    gift = json.dumps([{"msg_id": "g1", "nickname": "乙", "gift_num": 3}])
    assert inbox.accept_callback("live_gift", gift) == 1
    rows = inbox.since(0)
    assert [row["content"] for row in rows] == ["在吗", "送出 礼物×3"]
    assert rows[0]["source"] == "callback"
    assert inbox.since(rows[0]["seq"])[0]["msg_id"] == "g1"


def test_callback_signature_is_md5_of_sorted_headers_body_and_secret():
    headers = {
        "x-timestamp": "456789",
        "x-nonce-str": "123456",
        "x-roomid": "268",
        "x-msg-type": "live_gift",
    }
    body = "abc123你好"
    secret = "123abc"
    signed = callback_signature(headers, body, secret)
    assert signature_ok({**headers, "x-signature": signed}, body, secret)
    assert not signature_ok({**headers, "x-signature": "nope"}, body, secret)
    assert signature_ok(headers, body, "")
