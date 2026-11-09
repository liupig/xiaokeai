import asyncio
import time
from types import SimpleNamespace

from app.modules.glance import along
from app.modules.glance.journal import Journal
from app.modules.glance.situation import Offer, Situation
from app.modules.glance.watch import WatchSession


def test_journal_records_emotion_loops_highlights_and_reloads_previous_session(tmp_path):
    from app.modules.glance import archive

    archive.bind(tmp_path, packed=False)
    journal = Journal()
    journal.bind("movie:海上钢琴师")
    journal.note_speech("这句好扎心，你觉得呢？", mood="悲伤", cause="舱门告别")
    journal.note_user("嗯")
    situation = SimpleNamespace(scene="movie", title="海上钢琴师", object_id="movie:海上钢琴师")
    view = journal.view(situation)
    assert "当前情绪：悲伤" in view
    assert "没接上的话头" in view
    assert "高光" in view
    assert "他刚才：嗯" in view
    journal.save()

    reopened = Journal()
    reopened.bind("movie:海上钢琴师")
    opening = reopened.opening()
    assert "上次一起看过" in opening
    assert "这句好扎心" in opening
    assert reopened.opening() == ""
    assert "上次同内容的记忆" in reopened.view(situation)


def test_company_track_respects_quiet_time_and_five_minute_limit(monkeypatch):
    from app.modules.glance.journal import journal

    journal.reset()
    now = time.time()
    journal.user_at = now - 200
    situation = Situation()
    situation.scene = "movie"
    situation.object_id = situation.latest_object_id = "movie:clip"
    state = along._State(on=True, spoke_at=now - 200)
    monkeypatch.setattr(along, "situation", situation)
    monkeypatch.setattr(along, "_state", state)

    offer = along._direct_company_offer()
    assert offer is not None and offer.kind == "company" and offer.direct
    state.company_at = now
    assert along._direct_company_offer() is None
    state.company_at = 0
    situation.talk = "quiet"
    assert along._direct_company_offer() is None


def test_short_user_reaction_is_recorded_without_invalidating_candidate(monkeypatch):
    from app.modules.glance.journal import journal

    journal.reset()
    now = time.time()
    offer = Offer("movie", "movie:clip", "topic", now, 1, "字幕", direct=True, spoken="反应")
    state = along._State(on=True, pending="字幕", offer=offer)
    situation = Situation()
    watch = WatchSession(situation)
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "situation", situation)
    monkeypatch.setattr(along, "live", watch)

    along.note_user("嗯", 1, glance=True, harness=True, semantic=True)
    assert state.pending == "字幕"
    assert state.offer is offer
    assert state.epoch == 0
    assert journal.reactions[-1]["text"] == "嗯"


def test_visual_side_generation_finishes_before_offer_can_be_queued(monkeypatch, tmp_path):
    from app.modules.glance import archive
    from app.modules.glance.direct import direct_reply
    from app.modules.glance.journal import journal

    archive.bind(tmp_path, packed=False)
    journal.reset()
    situation = Situation()
    situation.scene = "movie"
    situation.object_id = situation.latest_object_id = "movie:clip"
    journal.bind("movie:clip")
    journal.note_speech("上一句反应", mood="温馨", cause="前一句")
    state = along._State(on=True, character_id=1)
    watch = WatchSession(situation)
    monkeypatch.setattr(along, "situation", situation)
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "live", watch)
    monkeypatch.setattr(along, "_direct_model", lambda _: ({"api_key": "test"}, "精简人设"))
    calls = []

    async def generated(conf, messages, **kwargs):
        calls.append(messages)
        return {
            "action": "speak", "text": "这句终于说出来了", "mood": "温馨",
            "generator": "chat", "attempts": [{"raw": "三行原文", "errors": [], "problem": ""}],
        }

    monkeypatch.setattr("app.modules.glance.direct.direct_reply", generated)
    offer = Offer("movie", "movie:clip", "topic", time.time(), 1, "字幕：终于说出来了", direct=True)
    result = along._prepare_direct(offer, "")
    assert result is offer
    assert offer.spoken == "这句终于说出来了"
    assert offer.generator == "chat"
    assert "精简人设" in calls[0][0]["content"]
    assert "她刚才已说过，避免重复：上一句反应" in calls[0][0]["content"]
    assert along.direct_result() == {}


def test_visual_three_line_protocol_has_change_mood_and_speech():
    from app.modules.glance.direct import parse_visual_protocol

    result = parse_visual_protocol("变化：舱门突然打开\n情绪：紧张\n台词：这开门声吓我一跳")
    assert result["action"] == "speak"
    assert result["change"] == "舱门突然打开"
    assert result["mood"] == "紧张"
    assert parse_visual_protocol("变化：没变\n情绪：平静\n台词：")["action"] == "silent"


def test_journal_builds_a_topic_from_dialogue_instead_of_static_frames():
    journal = Journal()
    journal.note_observation("画面手没动")
    journal.note_observation("字幕：还带我回家")
    journal.note_observation("字幕：虽然这个温暖可能很短暂")
    situation = SimpleNamespace(scene="video", title="抖音精选电脑版", object_id="video:feed")
    view = journal.view(situation)
    assert "还带我回家" in view
    assert "虽然这个温暖可能很短暂" in view
    assert "手没动" not in view
    assert "接着聊" in view
