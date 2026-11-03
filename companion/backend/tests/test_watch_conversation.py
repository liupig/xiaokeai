"""Session commands, immediate acknowledgement and grounded continuation."""
import threading
import time

import pytest

from app.modules.glance import along
from app.modules.glance.conversation import fast_request, followup, opening, parse_control, strip_opening
from app.modules.glance.situation import Situation, Offer
from app.modules.glance.watch import WatchSession
from app.services.llm import TagStreamParser


@pytest.fixture
def watching(monkeypatch):
    sit = Situation()
    sit.configure_watch(task="陪我看电影，留意人物关系")
    state = along._State(on=True, character_id=1)
    monkeypatch.setattr(along, "situation", sit)
    monkeypatch.setattr(along, "live", WatchSession(sit))
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "_halt", threading.Event())
    return sit, state


def test_current_task_survives_normal_chat_and_subsequent_changes(watching):
    sit, state = watching
    along.live.plan_standby = True
    along.note_user("多陪我说说话", 1, glance=True, harness=True, semantic=True)
    assert sit.talk == "more"
    assert not along.live.plan_standby
    revision = sit.watch_revision
    along.note_user("你觉得呢", 1, glance=True, harness=True, semantic=True)
    assert sit.talk == "more" and sit.watch_revision == revision
    assert "人物关系" in sit.watch_task
    response = along.configure('{"focus":"蓝衣服的人","task":"留意他手里的物品"}', 1, "盯一下他手里的东西")
    assert response["ok"] and response["talk"] == "more"
    assert response["focus"] == "蓝衣服的人"
    assert "留意他手里的物品" in along.eyes_context()
    assert along.snapshot()["contract"]["revision"] == revision + 1
    assert along.configure('{"talk":"quiet"}', 1)["ok"]
    assert state.speak_locked and along.live.speak_locked
    assert along.configure('{"talk":"normal","focus":""}', 1)["ok"]
    assert not state.speak_locked and not sit.attention


def test_updates_invalidate_old_commentary_without_restarting_vision(watching):
    sit, state = watching
    old = Offer("video", "video:clip", "topic", time.time(), 1, "原来的内容")
    state.offer = state.held = old
    state.pending = old.summary
    state.generated = "旧的评论"
    state.speaking = True
    response = along.configure('{"talk":"more"}', 1)
    assert response["ok"] and state.on
    assert state.offer is None and state.held is None
    assert not state.pending and not state.generated and not state.speaking
    assert not along.candidate_alive()
    revision = sit.watch_revision
    assert along.configure('{"talk":"more"}', 1)["revision"] == revision
    assert not along.configure('{"talk":"quiet"}', 2)["ok"]
    assert sit.talk == "more"


@pytest.mark.parametrize("value", ['{"talk":"always"}', '{"talk":false}', '{"launch":"game"}', '{bad', '[]'])
def test_invalid_commands_do_not_change_the_watch_contract(watching, value):
    sit, _ = watching
    before = sit.watch_contract()
    assert not along.configure(value, 1)["ok"]
    assert sit.watch_contract() == before


def test_first_observation_keeps_the_opening_and_actual_fact_in_context(watching, monkeypatch):
    sit, state = watching
    fact = "人物递出一封信"
    state.offer = Offer("movie", "movie:clip", "topic", time.time(), 1, fact, speech_rule="保持真实。" * 80)
    state.pending = fact
    state.trace_id = "one"
    along.register_opening("好呀，我陪你一起看。", 1)
    monkeypatch.setattr(along, "_preferences", lambda _: "")
    note = along.open_candidate(fact)
    assert fact in note and "同一轮的后半句" in note
    assert sit.watch_task in note
    assert state.opening
    along.finish_speak(True, "这封信来得挺突然的。")
    assert not state.opening
    assert sit.watch_contract()["spoken"] == "这封信来得挺突然的。"


def test_streamed_control_is_an_event_and_never_spoken():
    parser = TagStreamParser()
    events = parser.feed('[watch:{"talk":"mo') + parser.feed('re","focus":"人物关系"}]好，那我多跟你聊聊。')
    control = next(e for e in events if e["type"] == "watch")
    assert parse_control(control["value"]) == {"talk": "more", "focus": "人物关系"}
    assert "watch" not in "".join(e.get("delta", "") for e in events)


def test_acknowledgement_has_a_grounded_transition_without_duplicate_preface():
    lead = opening("陪看 一起看")
    assert lead == "好呀，我陪你一起看。"
    assert "同一轮" in followup(lead, continuous=True)
    assert strip_opening("我看看。我看看。门怎么突然开了？", lead) == "门怎么突然开了？"
    assert strip_opening(lead + "门开了。", lead) == "门开了。"


@pytest.mark.parametrize("text", ["不用一起看", "如果一起看呢", "一起看最新新闻", "一起看，帮我开游戏"])
def test_fast_path_does_not_override_other_intents(text):
    assert not fast_request(text)


def test_clear_watch_request_uses_fast_path():
    assert fast_request("一起看") == "陪看 一起看"
