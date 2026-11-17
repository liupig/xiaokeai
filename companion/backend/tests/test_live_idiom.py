"""直播多人对话与成语接龙：角色、回合和低延迟都走直播专用状态。"""
from app.modules.live.director import messages_for
from app.modules.live.events import LiveEvent
from app.modules.live.idiom import IdiomGame
from app.modules.live.queue import LiveQueue
from app.modules.live.host import LiveHost


def test_idiom_game_tracks_speakers_ai_turn_and_next_required_character():
    game = IdiomGame()
    game.active = True
    game.required = "为"
    game.last_ai = "事在人为"
    game.used.add(game.last_ai)

    wrong = game.respond("甲", "仁者见仁")
    assert "甲" in wrong and "要接“为”" in wrong and "先不算" in wrong
    first = game.respond("甲", "为所欲为")
    assert "甲" in first and "我接“为富不仁”" in first and "接“仁”" in first
    second = game.respond("乙", "仁者见仁")
    assert "乙" in second and "仁者见仁" in second and "我接" in second
    assert game.last_user == "仁者见仁" and game.last_nickname == "乙"
    assert game.last_ai != game.last_user

    reminder = game.respond("乙", "我出的，到你了")
    assert "乙出的是“仁者见仁”" in reminder
    assert f"我接的是“{game.last_ai}”" in reminder
    assert "现在轮到大家" in reminder


def test_dialogue_uses_real_user_and_assistant_roles():
    packet = messages_for([
        LiveEvent("bilibili", "comment", "丙", "继续"),
    ], name="清宵", persona="", phrase="", style="", mode="chat", audience="", recent=[],
        dialogue=[{"messages": [
            {"role": "user", "name": "甲", "content": "为所欲为"},
            {"role": "assistant", "name": "清宵", "content": "为富不仁"},
        ]}])
    assert packet[1] == {"role": "user", "content": "甲：为所欲为"}
    assert packet[2] == {"role": "assistant", "content": "为富不仁"}
    assert packet[-1]["role"] == "user" and "丙" in packet[-1]["content"]


def test_sparse_room_skips_long_batch_wait():
    queue = LiveQueue()
    cfg = {"features": {"scheduler": True, "reply": True},
           "pace": {"batch_sec": 4, "batch_size": 6, "user_cooldown_sec": 8}}
    event = LiveEvent("bilibili", "comment", "甲", "今天吃什么", uid="a", msg_id="m", ts=100)
    assert queue.offer(event, 100, cfg)
    assert queue.take_batch(100.4, cfg) is None
    picked = queue.take_batch(100.6, cfg)
    assert picked and picked[0].content == "今天吃什么"


def test_host_routes_idiom_without_waiting_for_llm():
    host = LiveHost()
    host.use_overrides({"compliance": {"strict": False}, "features": {"idle": False, "rundown": False}})
    host.on_air = True
    host.ingest(LiveEvent("bilibili", "comment", "甲", "我们玩成语接龙吧", uid="a", msg_id="s", ts=100), 100)
    host.tick_once(100.2)
    opening = host.snapshot()["turn"]
    assert opening["cue"] == "game" and "我先出" in opening["text"]
    host.ack(opening["id"], "completed")
    required = host.idiom.required
    assert required
    host.ingest(LiveEvent("bilibili", "comment", "乙", "仁者见仁", uid="b", msg_id="w", ts=101), 101)
    host.tick_once(101.2)
    assert "先不算" in host.snapshot()["turn"]["text"]
    assert host.idiom.last_user == ""
    assert host.idiom.required == required
