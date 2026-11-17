"""直播姬/OBS 的 B 站网页信息流：全部使用虚构响应，不访问真实房间。"""
from __future__ import annotations

import json

import brotli
import httpx

from app.modules.live.bili.packet import OP_NOTIFY, pack_packet, unpack_packets
from app.modules.live.bili.parse import events_from_json
from app.modules.live.bili.wbi import mixin_key, sign_params
from app.modules.live.bili.web import WebLiveSession, cookie_items, normalize_room
from app.modules.live.host import LiveHost
from app.modules.live.events import LiveEvent
from app.modules.live.queue import LiveQueue
from app.modules.live.selection import select_comments
from app.modules.live.director import idle_messages, messages_for, peel
from app.modules.live.commands import match_act


def test_wbi_signature_and_room_input():
    img = "7cd084941338484aae1ad9425b84077c"
    sub = "4932caff0ff746eab6f01bf08b70ac45"
    assert mixin_key(img, sub) == "ea1db124af3c7062474693fa704f4ff8"
    signed = sign_params({"id": 123, "web_location": "444.8"}, img, sub, timestamp=1_700_000_000)
    assert signed["wts"] == 1_700_000_000
    assert len(signed["w_rid"]) == 32
    assert signed == sign_params({"web_location": "444.8", "id": 123}, img, sub, timestamp=1_700_000_000)
    assert normalize_room("https://live.bilibili.com/12345?spm_id_from=444.8") == "12345"
    assert normalize_room(" 12345 ") == "12345"
    assert normalize_room("not a room") == ""
    assert dict(cookie_items("SESSDATA=abc; DedeUserID=42")) == {"SESSDATA": "abc", "DedeUserID": "42"}


def test_web_danmaku_and_brotli_packet_enter_common_event_shape():
    payload = json.dumps({
        "cmd": "DANMU_MSG",
        "info": [
            [0] * 15 + [{"extra": json.dumps({"id_str": "dm-1"})}],
            "主播晚上好",
            [42, "观众甲"],
        ],
        "send_time": 1_700_000_000_000,
    }).encode()
    wrapped = pack_packet(OP_NOTIFY, brotli.compress(pack_packet(OP_NOTIFY, payload)), proto=3)
    packets, rest = unpack_packets(wrapped)
    assert rest == b""
    event = events_from_json(packets[0][1])[0]
    assert (event.platform, event.kind, event.uid, event.nickname) == ("bilibili", "comment", "42", "观众甲")
    assert (event.content, event.msg_id) == ("主播晚上好", "dm-1")

    gift = events_from_json(json.dumps({
        "cmd": "SEND_GIFT",
        "data": {"uid": 7, "uname": "观众乙", "giftName": "小花花", "num": 2, "price": 1000, "msg_id": "g1"},
    }))[0]
    assert gift.kind == "gift" and gift.count == 2 and gift.price == 1000


def test_prepare_gets_real_room_buvid_and_signed_token(monkeypatch):
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/x/frontend/finger/spi":
            return httpx.Response(200, json={"code": 0, "data": {"b_3": "generated-buvid"}})
        if path == "/room/v1/Room/room_init":
            assert request.url.params["id"] == "123"
            return httpx.Response(200, json={"code": 0, "data": {"room_id": 987654}})
        if path == "/x/web-interface/nav":
            return httpx.Response(200, json={"code": -101, "data": {"wbi_img": {
                "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
            }}})
        if path == "/xlive/web-room/v1/index/getDanmuInfo":
            assert request.url.params["id"] == "987654"
            assert request.url.params["w_rid"] and request.url.params["wts"]
            assert "generated-buvid" in request.headers.get("cookie", "")
            return httpx.Response(200, json={"code": 0, "data": {
                "token": "token", "host_list": [{"host": "broadcastlv.chat.bilibili.com", "wss_port": 443}],
            }})
        raise AssertionError(path)

    transport = httpx.MockTransport(handler)

    def client_factory(*args, **kwargs):
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    session = WebLiveSession("123", "DedeUserID=42; SESSDATA=secret", lambda _ev: None, lambda _st: None)
    info = session._prepare()
    assert info["room_id"] == 987654
    assert info["wss"] == "wss://broadcastlv.chat.bilibili.com:443/sub"
    assert info["auth"]["uid"] == 42
    assert info["auth"]["roomid"] == 987654
    assert info["auth"]["buvid"] == "generated-buvid"


def test_host_selects_web_mode_without_touching_open_platform(monkeypatch):
    from app.modules.live.bili import web

    made = {}

    class FakeSession:
        def __init__(self, room, cookie, on_event, on_status):
            made.update(room=room, cookie=cookie, on_event=on_event, on_status=on_status)
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

        def snapshot(self):
            return {"state": "connecting" if self.started else "idle", "mode": "web", "room_id": "123"}

    monkeypatch.setattr(web, "WebLiveSession", FakeSession)
    host = LiveHost()
    host.use_overrides({"bilibili": {"mode": "web", "room_id": "https://live.bilibili.com/123", "cookie": "x=y"}})
    host.ensure_loop = lambda: None
    result = host.start_bilibili()
    assert result["ok"] and result["mode"] == "web"
    assert made["room"] == "123" and made["cookie"] == "x=y"
    assert made["on_event"] == host.ingest
    host.stop_bilibili()


def test_emote_does_not_spend_a_reply_and_substantive_question_wins():
    queue = LiveQueue()
    emote = LiveEvent("bilibili", "comment", "观众", "[星汐收藏集_？]", uid="e", msg_id="e1", ts=100)
    assert not queue.offer(emote, 100, {"features": {"scheduler": True}, "pace": {"user_cooldown_sec": 1}})
    picked = select_comments([
        emote,
        LiveEvent("bilibili", "comment", "甲", "？", uid="a", msg_id="a", ts=100),
        LiveEvent("bilibili", "comment", "丙", "0", uid="c", msg_id="c", ts=100),
        LiveEvent("bilibili", "comment", "乙", "无糖酸奶为什么难喝", uid="b", msg_id="b", ts=100),
    ], 100, 3, {})
    assert [item.content for item in picked] == ["无糖酸奶为什么难喝"]
    assert select_comments([emote], 100, 3, {}) == []


def test_public_live_rules_override_private_companion_persona():
    packet = messages_for([
        LiveEvent("bilibili", "comment", "观众", "晚上好"),
    ], name="清宵", persona="犬系女友。默认叫对方宝，只认定一个用户。", phrase="我在呢",
        style="", mode="chat", audience="", recent=[])
    system = packet[0]["content"]
    assert system.index("直播公开场景补充") > system.index("犬系女友")
    assert "不要使用宝、亲爱的等私密称呼" in system
    assert "不要编造和任何观众的私人关系" in system
    idle = idle_messages(name="清宵", persona="犬系女友，默认叫宝", phrase="我在呢",
                         style="", seed="打个招呼", audience="")
    assert "直播公开场景补充" in idle[0]["content"]


def test_live_speech_removes_tokens_markdown_and_directives():
    raw = ("<think>秘密推理</think><|im_start|>assistant\n"
           "```markdown\n**大家好** [微笑] [act:wave] <br> # 欢迎来到直播间\n"
           "- 第一条<|endoftext|>")
    spoken, _cue = peel(raw)
    assert "秘密推理" not in spoken and "<|" not in spoken
    assert "think" not in spoken and "assistant" not in spoken
    assert "markdown" not in spoken and "**" not in spoken
    assert "[微笑]" not in spoken and "[act:wave]" not in spoken and "<br>" not in spoken
    assert "#" not in spoken and "- 第一条" not in spoken
    assert "大家好" in spoken and "欢迎来到直播间" in spoken and "第一条" in spoken


def test_named_dance_request_is_a_real_stage_command():
    assert match_act("跳个舞吧") == "dance"
    assert match_act("跳个极乐净土") == "dance"
    assert match_act("倒是跳呀") == "dance"
    assert match_act("你今天心跳快吗") == ""


def test_current_character_prefix_is_removed_but_normal_colon_stays():
    assert peel("心月狐：好，换一支新的给你。", name="心月狐")[0] == "好，换一支新的给你。"
    assert peel("清宵: 大家好", name="清宵")[0] == "大家好"
    assert peel("重点是：今天别加班", name="清宵")[0] == "重点是：今天别加班"
