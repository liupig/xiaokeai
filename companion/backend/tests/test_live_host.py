"""直播主持：排队、礼物、节目单、花费、哔哩哔哩开放平台包。不连真房间。"""
from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.flags import MODULE_KEYS, _DEFAULT_OFF  # noqa: E402
from app.modules.live.bili.packet import OP_NOTIFY, pack_packet, unpack_packets  # noqa: E402
from app.modules.live.bili.parse import events_from_json  # noqa: E402
from app.modules.live.bili.sign import signed_headers  # noqa: E402
from app.modules.live.config import missing_acks, normalize, song_titles  # noqa: E402
from app.modules.live.director import canned, peel  # noqa: E402
from app.modules.live.events import LiveEvent  # noqa: E402
from app.modules.live.host import LiveHost  # noqa: E402
from app.modules.live.queue import LiveQueue  # noqa: E402
from app.modules.live.rundown import segments  # noqa: E402
from app.modules.live.show import GuessGame, WishPool  # noqa: E402


def _cfg(**features: bool) -> dict:
    cfg = normalize({})
    cfg["compliance"]["strict"] = False
    for key, value in features.items():
        cfg["features"][key] = value
    return cfg


def test_live_module_defaults_off_and_features_default_on():
    assert "live" in MODULE_KEYS
    assert "live" in _DEFAULT_OFF
    cfg = normalize({"douyin": {"room": "1"}})
    assert cfg["features"]["reply"] is True
    assert cfg["features"]["rehearsal"] is False
    assert cfg["bilibili"]["app_id"] == 0
    assert cfg["pace"]["batch_sec"] == 4
    assert missing_acks(normalize({})) == ["voice", "model", "bgm"]
    assert missing_acks(_cfg()) == []


def test_queue_cools_down_one_viewer_and_lets_gifts_cut_in():
    cfg = _cfg()
    queue = LiveQueue()
    now = 1_000.0
    assert queue.offer(LiveEvent("bilibili", "comment", "甲", "第一句", uid="a", msg_id="c1", ts=now), now, cfg)
    assert not queue.offer(LiveEvent("bilibili", "comment", "甲", "第二句", uid="a", msg_id="c2", ts=now + 1), now + 1, cfg)
    assert queue.offer(LiveEvent("bilibili", "gift", "乙", "送出 小电视×1", gift="小电视", count=1, msg_id="g1", ts=now + 1), now + 1, cfg)
    jumped = queue.take_priority(cfg)
    assert [item.nickname for item in jumped] == ["乙"]
    assert queue.take_batch(now + 1, cfg) is None
    batch = queue.take_batch(now + 20, cfg)
    assert batch is not None
    assert batch[0].content == "第一句"


def test_guess_and_wish_and_song_gate():
    game = GuessGame()
    assert game.should_announce(0)
    text = game.announce(0)
    assert "1 到 10" in text
    assert game.answer("甲", game.secret) == f"甲猜的 {game.secret}，中了。"
    assert not game.open
    pool = WishPool()
    pool.note(LiveEvent("bilibili", "comment", "乙", "许愿：明天天晴"))
    assert pool.pending() == 1
    assert pool.pop()["text"] == "明天天晴"
    cfg = _cfg()
    assert all(sid != "dance" for sid, _sec in segments(cfg))
    cfg["compliance"]["bgm_licensed"] = True
    cfg["songs"] = "自作的歌\n另一首"
    assert song_titles(cfg) == ["自作的歌", "另一首"]
    assert any(sid == "dance" for sid, _sec in segments(cfg))
    assert any(sid == "song" for sid, _sec in segments(cfg))


def test_bilibili_packet_roundtrip_and_signature_shape():
    payload = json.dumps({
        "cmd": "LIVE_OPEN_PLATFORM_DM",
        "data": {"uname": "甲", "msg": "晚上好", "msg_id": "m1", "open_id": "o1"},
    }, ensure_ascii=False).encode("utf-8")
    wrapped = pack_packet(OP_NOTIFY, zlib.compress(pack_packet(OP_NOTIFY, payload)), proto=2)
    first, rest = unpack_packets(wrapped[:10])
    assert first == []
    packets, rest = unpack_packets(wrapped)
    assert rest == b""
    assert packets[0][0] == OP_NOTIFY
    events = events_from_json(packets[0][1])
    assert events[0].nickname == "甲"
    assert events[0].content == "晚上好"
    gift = events_from_json(json.dumps({
        "cmd": "LIVE_OPEN_PLATFORM_SEND_GIFT",
        "data": {"uname": "乙", "gift_name": "小电视", "gift_num": 2, "price": 1000, "msg_id": "g"},
    }))
    assert gift[0].kind == "gift"
    assert gift[0].priority() > events[0].priority()
    headers = signed_headers("id", "secret", b"{}", nonce="n", timestamp="1")
    assert headers["x-bili-signature-method"] == "HMAC-SHA256"
    assert headers["Authorization"] != signed_headers("id", "other", b"{}", nonce="n", timestamp="1")["Authorization"]
    assert "\n" in "".join(f"{key}:{headers[key]}\n" for key in sorted(k for k in headers if k.startswith("x-bili-")))


def test_host_thanks_a_gift_without_calling_the_model_and_blocks_glance():
    host = LiveHost()
    cfg = _cfg(reply=False)
    called = {"n": 0}

    def complete(_conf, _messages):
        called["n"] += 1
        return "不该走到这", 10

    host.use_overrides(cfg, name="清宵", complete=complete)
    host.on_air = True
    host._last_spoke = 0
    assert host.ingest(LiveEvent("bilibili", "gift", "甲", "送出 小电视×1", gift="小电视", count=1, msg_id="g1"))
    host.tick_once(now=10_000)
    assert host._turn is not None
    assert "谢谢甲的小电视" in host._turn["text"]
    assert host._turn["interrupt"] is False
    assert called["n"] == 0
    assert host.on_air and cfg["features"]["content_gate"]
    spoken, cue = peel("[dance:a.vmd] 我跳一段。")
    assert cue == "dance"
    assert "[" not in spoken
    text, thank = canned([LiveEvent("douyin", "superchat", "丙", "看这里")], "我在呢")
    assert "醒目留言" in text
    assert thank == "gift"


def test_host_refuses_to_go_on_air_until_rights_are_acked_and_trips_budget():
    host = LiveHost()
    host.use_overrides(normalize({}), name="清宵")
    refused = host.go_on(1, now=1)
    assert refused["ok"] is False
    assert refused["missing"] == ["voice", "model", "bgm"]
    cfg = _cfg()
    cfg["budget"]["cap_cny"] = 0.01
    cfg["budget"]["cny_per_1k"] = 1
    host.use_overrides(cfg, name="清宵", complete=lambda _c, _m: ("模型说的", 100))
    host.budget.add(cfg, 100)
    assert host.budget.tripped(cfg)
    host.on_air = True
    host._last_spoke = 0
    host.ingest(LiveEvent("bilibili", "comment", "甲", "在吗", uid="a", msg_id="c9", ts=1))
    host.tick_once(now=30)
    assert host._turn is not None
    assert "模型说的" not in host._turn["text"]
    assert "在吗" in host._turn["text"]


def test_content_gate_blocks_screen_narration_only_while_on_air():
    from app.modules.live.compliance import blocks_glance
    from app.modules.live.host import host as singleton

    saved = (singleton.on_air, singleton._override, singleton._name, singleton._complete)
    singleton.use_overrides(_cfg(), name="清宵")
    singleton.on_air = True
    try:
        assert blocks_glance()
        singleton.on_air = False
        assert not blocks_glance()
    finally:
        singleton.on_air, singleton._override, singleton._name, singleton._complete = saved


def test_short_danmaku_becomes_a_stage_action_and_blocklist_stays_off_the_board():
    host = LiveHost()
    cfg = _cfg(reply=False)
    cfg["block_words"] = "广告\n加微"
    host.use_overrides(cfg, name="清宵")
    host.on_air = True
    host._last_spoke = 0
    assert not host.ingest(LiveEvent("bilibili", "comment", "甲", "来看广告", uid="a", msg_id="ad"))
    assert len(host._board) == 0
    assert host.ingest(LiveEvent("bilibili", "comment", "乙", "头发乱是吧", uid="b", msg_id="hair"))
    host.tick_once(now=10_000)
    assert host._turn is not None
    assert host._turn["act"] == "stretch"
    assert "顺一下" in host._turn["text"]


def test_song_request_only_when_the_title_is_licensed():
    host = LiveHost()
    cfg = _cfg(rundown=False, idle=False, reply=False)
    cfg["songs"] = "自作的歌"
    host.use_overrides(cfg, name="清宵")
    host.on_air = True
    host._last_spoke = 0
    host.ingest(LiveEvent("bilibili", "comment", "甲", "点歌《自作的歌》", uid="a", msg_id="s1", ts=10_000))
    host.tick_once(now=10_000)
    assert host._turn is None
    host.cfg()["compliance"]["bgm_licensed"] = True
    host.tick_once(now=10_001)
    assert host._turn is not None
    assert host._turn["cue"] == "song"
    assert "自作的歌" in host._turn["text"]


def test_session_cap_stops_and_quiet_zero_does_not():
    host = LiveHost()
    cfg = _cfg()
    cfg["pace"]["session_max_min"] = 1
    host.use_overrides(cfg, name="清宵")
    host.on_air = True
    host.health.started = 1_000
    host.tick_once(now=1_000 + 70)
    assert host.on_air is False
    assert "已停播" in host.health.last_error

    host = LiveHost()
    cfg = _cfg(idle=False)
    cfg["pace"]["quiet_min"] = 0
    host.use_overrides(cfg, name="清宵")
    host.on_air = True
    host.health.started = 1_000
    host._last_audience = 1_000
    host.tick_once(now=1_000 + 60 * 60)
    assert host.on_air is True
