"""State, event binding, real delivery acknowledgements and failure recovery."""
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.sight import service, session
from app.modules.sight.league import result
from app.modules.sight.league_client import parse_state
from app.modules.glance import along
from app.modules.glance.router import router
from app.modules.glance.situation import Offer

GAME = ("League of Legends.exe", "League of Legends", "League of Legends")


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGHT_HOME", str(tmp_path))
    service.reload()
    service.reset()
    monkeypatch.setattr(along, "_state", along._State(on=True, character_id=1))
    monkeypatch.setattr(along, "live", along.WatchSession())
    monkeypatch.setattr(along, "situation", along.live.situation)
    yield
    service.reset()


def seed():
    service.commit(*GAME, "")
    return service.commit(*GAME, "英雄：乐芙兰\n画面：旁边有一排小兵\n原文：旧字幕")


def test_identity_is_not_the_camera_target_and_transient_facts_are_replaced():
    seed()
    brief = service.commit(*GAME, "英雄：盖伦\n镜头英雄：盖伦\n画面：镜头移到上路")
    assert brief.slots["hero"] == "乐芙兰"
    assert "旧字幕" not in brief.handoff
    assert "镜头移到上路" in brief.handoff


@pytest.mark.parametrize("text", ["还没有出现胜利或失败的结算面板", "没有胜利", "如果胜利", "胜利或失败", "不确定是胜利"])
def test_negation_and_ambiguity_never_settle_a_game(text):
    seed()
    assert result(text) == ""
    assert service.commit(*GAME, "画面：" + text).phase != "score"


def test_current_state_uses_latest_frame_and_labels_previous_actions_as_history():
    seed()
    brief = service.commit(*GAME, "第1张：团战已经爆发\n第2张：返回于 14")
    assert brief.phase == "dead"
    assert "刚才" in brief.handoff
    assert "返回于 14" in brief.handoff
    revived = service.commit(*GAME, "画面：乐芙兰已经复活，正在补刀")
    assert revived.phase == "lane"
    assert "返回于 14" not in revived.handoff


def test_expired_action_is_not_repeated_from_memory():
    seed()
    with patch.object(session.time, "time", return_value=time.time() + 60):
        assert "旧字幕" not in service.current().handoff
        assert service.current().slots["hero"] == "乐芙兰"


def test_freshness_uses_new_phase_instead_of_latching_a_death_deadline():
    from app.modules.sight.league import observation_timing
    timing = observation_timing("dead", "画面：角色正在施放技能", 7.1)
    assert timing["freshness_phase"] == "lane"
    assert float(timing["capture_age"]) < float(timing["freshness_limit"])
    dead = observation_timing("lane", "原文：返回于 12", 7.1)
    assert float(dead["capture_age"]) > float(dead["freshness_limit"])


def test_end_button_is_terminal_without_inventing_a_win_or_loss():
    seed()
    brief = service.commit(*GAME, "原文：继续游戏")
    assert brief.phase == "score"
    assert "这局结束了" in brief.handoff
    assert "胜利" not in brief.handoff and "失败" not in brief.handoff


def test_new_selection_does_not_carry_last_match_hero():
    seed()
    brief = service.commit("LeagueClientUx.exe", "League of Legends", "League of Legends", "原文：选择你的英雄！")
    assert brief.phase == "select"
    assert brief.slots.get("hero") in {"", "没看清", None}


def test_local_telemetry_resolves_the_player_instead_of_first_player():
    state = parse_state({"activePlayer": {"summonerName": "me"}, "allPlayers": [
        {"summonerName": "other", "championName": "Garen"},
        {"summonerName": "me", "championName": "LeBlanc", "isDead": True, "respawnTimer": 14},
    ], "gameData": {"gameTime": 120}})
    assert state["hero"] == "LeBlanc"
    assert state["dead"] is True
    assert parse_state({"activePlayer": {}, "allPlayers": [{"championName": "Garen"}]}) == {}


def queue():
    item = Offer("game", "league", "event-1", time.time(), 1, "乐芙兰锁链命中了", speech_rule="只接这一下", max_age=12)
    with along._lock:
        along._enqueue(item, "")
    return item


def test_queued_event_remains_bound_when_visual_state_changes():
    seed()
    queue()
    service.commit(*GAME, "原文：胜利")
    told = along.candidate_instruction("接一句")
    assert "锁链命中了" in told
    assert "胜利" not in told


@pytest.mark.parametrize("status", ["completed", "failed", "interrupted", "displayed"])
def test_generation_is_not_a_playback_acknowledgement(status):
    queue()
    along.generated("这下挂住了")
    assert along.live.speeches == []
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    seq = along.snapshot()["seq"]
    client.post("/api/modules/glance/along/ack", json={"seq": seq - 1, "status": "completed"})
    assert along.live.speeches == []
    response = client.post("/api/modules/glance/along/ack", json={"seq": seq, "status": status})
    assert response.status_code == 200
    assert along.live.speeches == (["这下挂住了"] if status == "completed" else [])
    client.post("/api/modules/glance/along/ack", json={"seq": seq, "status": status})
    assert len(along.live.speeches) <= 1


def test_combat_event_expires_by_capture_time():
    item = queue()
    item.observation_time -= 13
    assert not along.candidate_alive()


def test_multiframe_prompt_keeps_history_for_both_vision_providers():
    from app.modules.glance.vision import _prompt

    text = _prompt("看这一局", "他刚说想练锁链", False)
    assert "看这一局" in text and "想练锁链" in text


def test_template_echo_cannot_become_a_hero_or_equipment():
    seed()
    brief = service.commit(*GAME, "英雄：玩家自己的英雄\n装备：已购买的装备，悬停和推荐不算\n画面：乐芙兰回到泉水")
    assert brief.slots["hero"] == "乐芙兰"
    assert "玩家自己的英雄" not in brief.handoff
    assert "已购买的装备" not in brief.handoff


def test_verified_bot_loading_card_uses_player_labels_not_card_position():
    from app.modules.sight.screen_text import facts

    text = facts([{"text": "光辉女郎（电脑）"}, {"text": "扭曲树精（电脑）"},
                  {"text": "源代码 乐芙兰 梦幻闪击"}])
    assert "英雄：乐芙兰" in text
    assert not any(line.startswith("英雄：") for line in facts([{"text": "乐芙兰"}, {"text": "光辉女郎"}]).splitlines())


def test_native_ocr_verifies_words_instead_of_repeating_model_inventions():
    from app.modules.sight.screen_text import verify

    text = verify("画面：在清兵\n原文：不存在的名字", [{"text": "源 代 码 乐 芙 兰"}])
    assert "在清兵" in text
    assert "不存在" not in text


def test_death_countdowns_do_not_trigger_repeated_condolences():
    from app.modules.glance.game_director import cadence

    assert cadence("dead", "返回于 14", talk="normal", elapsed=1, opening=False)
    assert not cadence("dead", "返回于 10", talk="normal", elapsed=4, opening=False, same_phase=True)
    assert not cadence("lane", "在清兵", talk="normal", elapsed=3, opening=False)
    assert cadence("score", "胜利", talk="normal", elapsed=3, opening=False)


def test_learning_player_identity_is_new_even_if_loading_sentence_is_contained():
    from app.modules.glance.situation import Situation, parse_observation

    sit = Situation()
    first = sit.ingest(parse_observation("类型：game\n标题：英雄联盟\n原文：正在进这局", timestamp=1))
    assert first is not None
    sit.note_offered(True)
    known = sit.ingest(parse_observation("类型：game\n标题：英雄联盟\n原文：乐芙兰正在进这局", timestamp=2))
    assert known is not None
    assert "乐芙兰" in known.summary


@pytest.mark.parametrize("spoken", ["赢了，你这把五杀真帅", "宝你往后挪挪", "宝快往后撤一下", "装备栏还空着呢", "对面盖伦很强"])
def test_role_flavor_cannot_invent_combat_facts_or_orders(spoken):
    from app.modules.glance.game_director import unsupported_reply

    assert unsupported_reply("这局结束了，乐芙兰，胜利", spoken)


def test_unverified_draft_is_repaired_before_it_reaches_speech(monkeypatch):
    import asyncio
    from app.services import llm
    from app.modules.glance.game_director import grounded_reply

    calls = []

    async def model(conf, messages):
        calls.append(messages)
        yield {"type": "emo", "value": "happy"}
        yield {"type": "text", "delta": "五杀太帅了" if len(calls) == 1 else "赢啦，宝这把拿下了！"}
        yield {"type": "done"}

    monkeypatch.setattr(llm, "stream_chat", model)
    answer = asyncio.run(grounded_reply({}, [], evidence="乐芙兰，胜利", topic="game"))
    assert len(calls) == 2
    assert answer["action"] == "speak"
    assert "五杀" not in answer["text"]
    assert answer["performance"] == [{"type": "emo", "value": "happy"}]
