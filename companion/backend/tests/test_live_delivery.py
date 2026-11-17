"""商业交付底座：审计、观众关系、播放回执和冷场节奏。"""
from __future__ import annotations

import time

from app.modules.live.audience import AudienceBook
from app.modules.live.events import LiveEvent
from app.modules.live.host import LiveHost
from app.modules.live.journal import LiveJournal
from app.routers.chat import ChatRequest
from app.routers.chat import history as chat_history
from app.models import ChatMessage
from sqlmodel import SQLModel, Session, create_engine


def test_journal_records_event_turn_ack_and_latency(tmp_path):
    journal = LiveJournal(tmp_path / "live.sqlite3")
    sid = journal.start(7, {"mode": "web", "room_id": "123"})
    now = time.time()
    journal.append("event", {"kind": "comment", "nickname": "甲", "content": "加班到十点", "ts": int(now * 1000)})
    journal.append("turn", {"id": "t1", "text": "晚饭吃了吗", "sources": [{"ts": int(now * 1000)}]}, now + 1.25)
    journal.append("ack", {"turn_id": "t1", "outcome": "completed", "player_id": "stage"})
    journal.end()

    assert journal.sessions()[0]["id"] == sid
    assert [row["kind"] for row in journal.trace(sid)] == ["session_start", "event", "turn", "ack", "session_end"]
    metrics = journal.metrics(sid)
    assert metrics["events"] == 1 and metrics["turns"] == 1
    assert metrics["acks"] == {"completed": 1}
    assert abs(metrics["source_to_turn_avg_sec"] - 1.25) < 0.002


def test_host_emits_auditable_receipts_without_touching_personal_chat(tmp_path):
    journal = LiveJournal(tmp_path / "live.sqlite3")
    journal.start(1, {"mode": "web", "room_id": "123"})
    host = LiveHost()
    host._journal = journal
    host.use_overrides({"compliance": {"strict": False}, "features": {"reply": True, "idle": False, "rundown": False}})
    host.on_air = True
    host.ingest(LiveEvent("bilibili", "comment", "甲", "今天加班到十点", uid="a", msg_id="m1"), time.time())
    host.tick_once(time.time() + 1)
    turn = host.snapshot()["turn"]
    assert turn and turn["sources"][0]["nickname"] == "甲"
    assert host.claim(turn["id"], "stage")
    assert host.ack(turn["id"], "completed", "stage")
    host.go_off()
    metrics = journal.metrics(journal.session_id)
    assert metrics["events"] == 1 and metrics["turns"] == 1 and metrics["acks"]["completed"] == 1


def test_audience_context_keeps_previous_words_with_the_right_viewer():
    book = AudienceBook()
    first = LiveEvent("bilibili", "comment", "甲", "今天加班到十点", uid="a")
    book.note(first)
    current = LiveEvent("bilibili", "comment", "甲", "晚饭还没吃", uid="a")
    book.note(current)
    book.note(LiveEvent("bilibili", "comment", "乙", "我下班去打球", uid="b"))
    book.note_reply("甲")
    context = book.context_for([current])
    assert "甲：本场发言2次，已被回复1次" in context
    assert "今天加班到十点" in context
    assert "下班去打球" not in context


def test_idle_backoff_increases_when_room_stays_quiet():
    host = LiveHost()
    host.use_overrides({"features": {"idle": True, "rundown": False}, "pace": {"idle_sec": 15}})
    host.on_air = True
    host._last_spoke = 0
    assert host._plan(16)["type"] == "idle"
    assert host._idle_level == 1
    assert host._plan(20) is None
    assert host._plan(31)["type"] == "idle"
    assert host._idle_level == 2


def test_guess_game_only_starts_when_viewer_asks():
    host = LiveHost()
    host.use_overrides({"features": {"idle": False, "rundown": True, "auto_games": False}})
    host.on_air = True
    host.ingest(LiveEvent("bilibili", "comment", "甲", "我们玩猜数字", uid="a", msg_id="g", ts=100), 100)
    host.tick_once(100.2)
    turn = host.snapshot()["turn"]
    assert turn["cue"] == "game" and "1 到 10" in turn["text"]
    host.ack(turn["id"], "completed")
    host.ingest(LiveEvent("bilibili", "comment", "甲", str(host.game.secret), uid="a", msg_id="n", ts=110), 110)
    host.tick_once(110.2)
    assert "中了" in host.snapshot()["turn"]["text"]


def test_original_chat_channel_defaults_to_personal_and_live_turn_delegates():
    req = ChatRequest(character_id=1, text="抽张塔罗")
    assert req.channel == "personal"
    live = ChatRequest(character_id=1, text="抽张塔罗", channel="live", viewer_name="甲", live_session_id="s1")
    assert live.viewer_name == "甲" and live.live_session_id == "s1"
    host = LiveHost()
    turn = host._batch_turn([], {"persona": {}}, "chat")
    assert turn["delivery"] == "original_chat" and turn["text"] == ""


def test_original_chat_ack_returns_real_assistant_text(tmp_path):
    journal = LiveJournal(tmp_path / "live.sqlite3")
    journal.start(1, {})
    host = LiveHost()
    host._journal = journal
    host.on_air = True
    host._turn = {"id": "t1", "text": ""}
    host._turn_context = {"viewers": [{"name": "甲", "text": "抽张塔罗"}], "reply": "",
                          "messages": [{"role": "user", "name": "甲", "content": "抽张塔罗"},
                                       {"role": "assistant", "name": "清宵", "content": ""}]}
    assert host.ack("t1", "completed", "stage", "我给你抽一张。")
    trace = journal.trace(journal.session_id)
    assert trace[-1]["data"]["text"] == "我给你抽一张。"


def test_personal_history_excludes_live_but_keeps_legacy_null_kind():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(ChatMessage(character_id=99, role="user", content="个人旧消息", kind=None))
        session.add(ChatMessage(character_id=99, role="user", content="个人新消息", kind="qa"))
        session.add(ChatMessage(character_id=99, role="user", content="甲：直播弹幕", kind="live"))
        session.commit()
        personal = chat_history(99, channel="personal", session=session)
        live = chat_history(99, channel="live", session=session)
    assert [row["content"] for row in personal] == ["个人旧消息", "个人新消息"]
    assert [row["content"] for row in live] == ["甲：直播弹幕"]
