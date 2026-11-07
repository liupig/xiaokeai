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
