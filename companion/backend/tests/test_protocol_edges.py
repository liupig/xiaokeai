from app.modules.live.bili.packet import OP_NOTIFY, pack_packet, unpack_packets
from app.services.llm import TagStreamParser


def test_parser_releases_plain_brackets_immediately():
    parser = TagStreamParser()

    events = parser.feed("数组 [1, 2] 和引用 [说明] 都直接说")

    assert "".join(event["delta"] for event in events) == "数组 [1, 2] 和引用 [说明] 都直接说"
    assert all(event["type"] == "text" for event in events)


def test_parser_preserves_split_tag():
    parser = TagStreamParser()

    assert parser.feed("开心[em") == [{"type": "text", "delta": "开心"}]
    assert parser.feed("o:happy]继续说") == [
        {"type": "emo", "value": "happy"},
        {"type": "text", "delta": "继续说"},
    ]


def test_bili_recovers_after_bad_header():
    packet = pack_packet(OP_NOTIFY, b'{"ok":1}')

    packets, rest = unpack_packets(b"not-a-valid-header" + packet)

    assert packets == [(OP_NOTIFY, b'{"ok":1}')]
    assert rest == b""


def test_bili_preserves_incomplete_packet():
    packet = pack_packet(OP_NOTIFY, b"body")

    packets, rest = unpack_packets(packet[:-1])

    assert packets == []
    assert rest == packet[:-1]


def test_expression_tag_carries_name_strength_and_duration_without_leaking():
    parser = TagStreamParser()
    assert parser.feed("[expr:頬染") == []
    assert parser.feed("め:0.65:2]我知道了。[expr:]") == [
        {"type": "expr", "value": "頬染め:0.65:2"},
        {"type": "text", "delta": "我知道了。"},
    ]
    assert parser.feed("[expr:頬染め:") == []
    assert parser.flush() == []


def test_expression_tag_attaches_to_following_voice_unit():
    import asyncio

    from app.services.duplex import annotate_stream

    async def source():
        yield {"type": "text", "delta": "先等等"}
        yield {"type": "expr", "value": "smile:0.7:2"}
        yield {"type": "text", "delta": "我想到一个办法。"}
        yield {"type": "done", "full_text": "先等等我想到一个办法。"}

    async def collect():
        return [event async for event in annotate_stream(source())]

    events = asyncio.run(collect())
    spoken_and_cues = [
        (event["type"], event.get("text") or event.get("value"))
        for event in events if event["type"] in {"speech", "expr"}
    ]
    assert spoken_and_cues == [
        ("speech", "先等等"),
        ("expr", "smile:0.7:2"),
        ("speech", "我想到一个办法。"),
    ]


def test_first_duplex_header_arrives_before_text_and_duplicate_is_ignored():
    import asyncio

    from app.services.duplex import annotate_stream
    from app.services.prompt_stack import guard_refusal

    async def source():
        parser = TagStreamParser()
        for chunk in ["[du", "plex:queue]", "[duplex:interrupt][emo:happy]", "好的。"]:
            for event in parser.feed(chunk):
                yield event
        yield {"type": "done", "full_text": "好的。"}

    async def collect():
        return [event async for event in annotate_stream(guard_refusal(source()))]

    events = asyncio.run(collect())
    assert events[0] == {"type": "duplex_decision", "duplex_cmd": "queue"}
    assert [event["duplex_cmd"] for event in events if event["type"] == "duplex_decision"] == ["queue"]
    assert all("[duplex:" not in event.get("delta", "") for event in events)


def test_first_complete_clause_reaches_speech_before_second_model_chunk():
    import asyncio

    from app.locale_pack import set_reply
    from app.services.duplex import annotate_stream
    from app.services.prompt_stack import guard_refusal

    async def run():
        set_reply("zh-CN")
        release = asyncio.Event()

        async def source():
            yield {"type": "duplex", "value": "queue"}
            yield {"type": "text", "delta": "我先陪你把这件事情理一理，"}
            await release.wait()
            yield {"type": "text", "delta": "剩下的慢慢说。"}
            yield {"type": "done", "full_text": "我先陪你把这件事情理一理，剩下的慢慢说。"}

        events = annotate_stream(guard_refusal(source(), early_clause=True), quick_first=True)
        try:
            assert (await anext(events))["type"] == "duplex_decision"
            assert (await anext(events))["type"] == "text"
            first = await asyncio.wait_for(anext(events), 0.3)
            assert first["type"] == "speech"
            assert "理一理" in first["text"]
            release.set()
            rest = [event async for event in events]
            assert any(event["type"] == "speech" and "慢慢说" in event["text"] for event in rest)
        finally:
            await events.aclose()

    asyncio.run(run())


def test_playback_latency_uses_the_same_turn_id_without_conversation_text(monkeypatch):
    from importlib import import_module

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    chat = import_module("app.routers.chat")
    writes = []
    monkeypatch.setattr(chat.talk_log, "write", lambda *args, **kwargs: writes.append((args, kwargs)))
    app = FastAPI()
    app.include_router(chat.router)
    response = TestClient(app).post("/api/chat/playback-latency", json={
        "latency_id": "turn-123",
        "stages_ms": {"tts_request": 2000, "tts_ready": 2450, "audible": 2500, "unknown": 12},
    })
    assert response.status_code == 204
    assert writes[0][1] == {
        "latency_id": "turn-123",
        "stages_ms": {"tts_request": 2000, "tts_ready": 2450, "audible": 2500},
    }


def test_duplex_header_after_prose_cannot_change_the_turn():
    import asyncio

    from app.services.duplex import annotate_stream

    async def collect():
        async def source():
            yield {"type": "text", "delta": "我先回答。"}
            yield {"type": "duplex", "value": "interrupt"}
            yield {"type": "done", "full_text": "我先回答。"}
        return [event async for event in annotate_stream(source())]

    assert all(event["type"] != "duplex_decision" for event in asyncio.run(collect()))
