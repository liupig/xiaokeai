"""Semantic action execution boundaries, without launching games or taking images."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.modules.harness import actions
from app.modules.glance import along, eyes_host
from app.modules.glance.service import glance_from_user
from app.services.llm import TagStreamParser


@pytest.mark.parametrize("text", ["帮我看一下今天金价", "一起看看最近新闻", "瞅瞅北京天气", "看看英雄联盟最新版本", "我在玩LOL，帮我查金价"])
def test_public_facts_never_authorize_vision(text):
    assert not actions.visual_request_allowed(text)
    assert glance_from_user(text) == ""


@pytest.mark.parametrize("text", ["你在干嘛呢", "你在干什么呢？", "你现在在干嘛", "我在干嘛"])
def test_status_chat_never_authorizes_vision(text):
    assert actions.visual_request_policy(text) == "chat"
    assert glance_from_user(text) == ""


@pytest.mark.parametrize("text", ["看看这个网页上的金价", "图里的天气图标在哪", "帮我看看屏幕上的报错", "这局你帮我盯一下"])
def test_explicit_screen_targets_allow_visual_action(text):
    assert actions.visual_request_allowed(text)


def test_ambiguous_followup_inherits_public_fact_boundary():
    assert not actions.visual_request_allowed("你帮我看一下", [{"role": "user", "content": "今天金价多少"}])


@pytest.mark.parametrize("text", ["你看一下", "帮我瞅一眼呗", "能不能帮忙看看这个？"])
def test_bare_requests_need_a_target(text):
    assert actions.visual_request_policy(text) == "clarify"
    assert actions.visual_request_policy(text, screen_context=True) == "allow"
    assert actions.visual_request_policy(text, [{"role": "user", "content": "屏幕上报错了"}]) == "allow"


@pytest.mark.parametrize("ask,continuous", [("瞅瞅屏幕报错", False), ("陪看 我这局", True), ("开启", True)])
def test_visual_action_can_start_on_demand_without_magic_phrase(monkeypatch, ask, continuous):
    started, enabled = [], []
    monkeypatch.setattr(eyes_host, "capability", lambda: {"available": True})
    monkeypatch.setattr(eyes_host, "ensure", lambda: "up")
    monkeypatch.setattr(eyes_host, "enable_glance", lambda: enabled.append(True))
    monkeypatch.setattr(along, "start", lambda cid, request="": started.append(cid))
    assert actions.prepare_visual(ask, 17, threading.Event()) == ""
    assert enabled == [True]
    assert started == ([17] if continuous else [])


def test_unavailable_vision_does_not_start_or_capture(monkeypatch):
    monkeypatch.setattr(eyes_host, "capability", lambda: {"available": False, "message": "尚未安装视觉"})
    def forbidden():
        raise AssertionError("must not start an unavailable environment")
    monkeypatch.setattr(eyes_host, "ensure", forbidden)
    assert actions.prepare_visual("看屏幕", 1, threading.Event()) == "尚未安装视觉"


def test_listening_port_does_not_mark_loading_model_ready(monkeypatch):
    monkeypatch.setattr(eyes_host, "_local", lambda: True)
    monkeypatch.setattr(eyes_host, "probe", lambda: True)
    monkeypatch.setattr(eyes_host, "_phase", "starting")
    monkeypatch.setattr(eyes_host, "_message", "")
    assert eyes_host.eyes_status()["eyes"] == "starting"
    assert eyes_host.ensure() == "starting"


def test_model_warmup_failure_is_preserved(monkeypatch):
    from types import SimpleNamespace
    from app.modules.glance import service as glance
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": False, "message": "显存不足"})
    client = SimpleNamespace(post=lambda *args, **kwargs: response)
    monkeypatch.setattr(glance, "_borrow", lambda: client)
    monkeypatch.setattr(glance, "_release", lambda _: None)
    monkeypatch.setattr(eyes_host, "_local", lambda: True)
    monkeypatch.setattr(eyes_host, "probe", lambda: True)
    monkeypatch.setattr(eyes_host, "_phase", "starting")
    monkeypatch.setattr(eyes_host, "_message", "")
    monkeypatch.setattr(eyes_host, "_token", 1)
    eyes_host._warmup(1)
    assert eyes_host.eyes_status() == {"eyes": "down", "message": "显存不足"}
    assert eyes_host.ensure() == "failed"


def test_stop_works_even_without_available_visual_environment(monkeypatch):
    called = []
    monkeypatch.setattr(along, "stop", lambda: called.append("stop"))
    monkeypatch.setattr(eyes_host, "shutdown", lambda: called.append("shutdown"))
    assert actions.prepare_visual("关闭", 1, threading.Event()) == "closed"
    assert called == ["stop", "shutdown"]


def test_semantic_path_does_not_start_vision_for_keywords(monkeypatch):
    def forbidden(*args):
        raise AssertionError("keywords cannot start semantic actions")
    monkeypatch.setattr(eyes_host, "ensure", forbidden)
    monkeypatch.setattr(eyes_host, "enable_glance", forbidden)
    monkeypatch.setattr(along, "start", forbidden)
    along.note_user("一起看看金价", 1, glance=False, harness=True, semantic=True)


def test_split_action_tags_do_not_reach_speech():
    parser = TagStreamParser()
    events = parser.feed("[play:英雄") + parser.feed("联盟][glance:陪看 这局]")
    assert events == [{"type": "play", "value": "英雄联盟"}, {"type": "glance", "value": "陪看 这局"}]


def test_game_action_uses_existing_launcher_without_sentence_matching(monkeypatch):
    from app.modules.play import service
    from app.modules.sight import service as sight
    called = []
    def open_game(name, **kwargs):
        called.append(name)
        return {"game": name, "state": "waiting", "platform_label": "WeGame"}
    monkeypatch.setattr(service, "open_game", open_game)
    monkeypatch.setattr(sight, "hold_name", lambda _: None)
    note = actions.play_note("英雄联盟", "zh-CN")
    assert called == ["英雄联盟"]
    assert "正在开" in note and "不要说已经进游戏" in note


def test_capability_check_never_launches_or_probes(monkeypatch, tmp_path):
    home = tmp_path / "eyes"; home.mkdir()
    (home / "app.py").write_text("", encoding="utf-8")
    python = home / "python.exe"; python.write_text("", encoding="utf-8")
    monkeypatch.setattr(eyes_host, "_local", lambda: True)
    monkeypatch.setattr(eyes_host, "_phase", "down")
    monkeypatch.setattr(eyes_host, "eyes_home", lambda: home)
    monkeypatch.setattr(eyes_host, "eyes_python", lambda _: python)
    from app.modules.glance import vision
    monkeypatch.setattr(vision, "vision_config", lambda: {"provider": "minicpm"})
    def forbidden():
        raise AssertionError("availability checks must be passive")
    monkeypatch.setattr(eyes_host, "probe", forbidden)
    monkeypatch.setattr(eyes_host, "ensure", forbidden)
    assert eyes_host.capability()["available"]


@pytest.mark.parametrize("enabled", [False, True])
def test_eyes_process_log_is_opt_in(monkeypatch, tmp_path, enabled):
    import subprocess
    from types import SimpleNamespace

    home = tmp_path / "eyes"
    home.mkdir()
    (home / "app.py").write_text("", encoding="utf-8")
    python = home / "python.exe"
    python.write_text("", encoding="utf-8")
    if enabled:
        monkeypatch.setenv("XIAOKE_EYES_LOG", "1")
    else:
        monkeypatch.delenv("XIAOKE_EYES_LOG", raising=False)
    monkeypatch.setattr(eyes_host, "_local", lambda: True)
    monkeypatch.setattr(eyes_host, "probe", lambda: False)
    monkeypatch.setattr(eyes_host, "_phase", "down")
    monkeypatch.setattr(eyes_host, "_proc", None)
    monkeypatch.setattr(eyes_host, "_log", None)
    monkeypatch.setattr(eyes_host, "eyes_home", lambda: home)
    monkeypatch.setattr(eyes_host, "eyes_python", lambda _: python)
    monkeypatch.setattr(eyes_host, "_listeners", lambda _: [])
    monkeypatch.setattr(eyes_host, "_bind", lambda _: None)
    monkeypatch.setattr(eyes_host, "_warmup", lambda _: None)
    launched = {}
    def popen(*args, **kwargs):
        launched.update(kwargs)
        return SimpleNamespace(pid=123)
    monkeypatch.setattr(eyes_host.subprocess, "Popen", popen)

    assert eyes_host.ensure() == "starting"
    assert launched["stdout"] is launched["stderr"]
    if enabled:
        assert launched["stdout"].name == str(home / "eyes-host.log")
        eyes_host._close_log(launched["stdout"])
    else:
        assert launched["stdout"] == subprocess.DEVNULL
        assert not (home / "eyes-host.log").exists()


@pytest.fixture
def chat_route(monkeypatch, tmp_path):
    """Exercise the real /api/chat coordinator with fake action/model backends."""
    import json
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, Session, create_engine
    from app import db, talk_log
    from app.models import Character
    from app.modules.flags import MODULE_KEYS
    from app.modules.harness import service as harness
    from app.modules.websearch import service as websearch
    from app.modules.glance import service as glance
    from app.routers import chat
    from app.services import settings_store, prompt_stack, coins

    database = create_engine(f"sqlite:///{tmp_path / 'chat.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(database)
    with Session(database) as session:
        session.add(Character(id=1, name="测试角色", persona="自然简短地聊天。")); session.commit()
    conf = {"llm": {"api_key": "test-dummy", "model": "test", "base_url": "https://unused.test"},
            "modules": {**{key: False for key in MODULE_KEYS}, "harness": True, "play": True},
            "locale": {"ui": "zh-CN", "reply": "zh-CN", "reply_mode": "fixed"}, "tts": {}}
    monkeypatch.setattr(db, "engine", database)
    monkeypatch.setattr(settings_store, "get_all", lambda _: conf)
    monkeypatch.setattr(prompt_stack, "build_messages", lambda **kwargs: [{"role": "system", "content": "测试角色"}] + kwargs["history"])
    monkeypatch.setattr(prompt_stack, "overlay_active", lambda _: False)
    monkeypatch.setattr(chat, "_after_reply", lambda *args: None)
    monkeypatch.setattr(talk_log, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(coins, "purse_line", lambda: "")
    monkeypatch.setattr(coins, "purse_say", lambda: "")
    monkeypatch.setattr(along, "note_user", lambda *args, **kwargs: None)
    monkeypatch.setattr(along, "release_user_turn", lambda: None)
    monkeypatch.setattr(along, "seed_seen", lambda _: None)
    monkeypatch.setattr(along, "snapshot", lambda: {"on": False})
    monkeypatch.setattr(eyes_host, "capability", lambda: {"available": True, "message": "视觉可按需启动"})
    state = {"initial": [], "calls": [], "actions": [], "captures": [], "visual_result": ""}

    async def model(_conf, **kwargs):
        text = kwargs["user_text"]
        state["calls"].append(text)
        if len(state["calls"]) == 1:
            for event in state["initial"]:
                yield event
            yield {"type": "done", "full_text": ""}
            return
        if text.startswith("【宿主事件：") or "这次需要联网" in text:
            if "这次需要联网" in text:
                yield {"type": "lookup", "value": "今日金价"}
                yield {"type": "done", "full_text": ""}
                return
            reply = "你想让我看什么？" if "对象不明确" in text else "好，按刚才的结果接着说。"
        elif text.startswith("页面到了"):
            reply = "查到的数字是500。"
        else:
            for event in state["initial"]:
                yield event
            yield {"type": "done", "full_text": ""}
            return
        yield {"type": "text", "delta": reply}
        yield {"type": "done", "full_text": reply}

    def visual(ask, *args):
        state["actions"].append(("vision", ask)); return state["visual_result"]
    def play(query, *args):
        state["actions"].append(("play", query)); return "【开游戏】正在打开英雄联盟。"
    def lookup(query):
        state["actions"].append(("lookup", query)); return "金价500。"
    monkeypatch.setattr(harness, "stream_reply", model)
    monkeypatch.setattr(actions, "prepare_visual", visual)
    monkeypatch.setattr(actions, "play_note", play)
    monkeypatch.setattr(websearch, "lookup_note", lookup)
    def capture(*args):
        state["captures"].append(args)
        return "【眼前】你正在玩英雄联盟。", ""
    monkeypatch.setattr(glance, "glance_bundle", capture)

    app = FastAPI(); app.include_router(chat.router)
    def session_dependency():
        with Session(database) as session:
            yield session
    app.dependency_overrides[db.get_session] = session_dependency
    client = TestClient(app)
    def send(text, initial, **extra):
        state["initial"] = initial
        response = client.post("/api/chat", json={"character_id": 1, "text": text, **extra})
        assert response.status_code == 200
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert not [event for event in events if event.get("type") == "error"]
        return events
    yield send, state
    client.close(); database.dispose()


def test_route_blocks_wrong_visual_choice_for_gold_price(chat_route):
    send, state = chat_route
    events = send("帮我看一下金价", [{"type": "glance", "value": "看屏幕"}])
    assert state["actions"] == [("lookup", "今日金价")]
    assert any(event.get("full_text", "").endswith("查到的数字是500。") for event in events)


def test_tarot_full_reading_prompt_reaches_model(chat_route, monkeypatch):
    from app.services import coins

    monkeypatch.setattr(coins, "purse_say", lambda: "你现在有 3794 枚金币。")
    send, state = chat_route
    prompt = "请结合原问题和所有已翻开的牌，给我完整解读。"
    events = send(prompt, [{"type": "text", "delta": "这是整组牌的完整解读。"}])
    assert state["calls"] == [prompt]
    assert not any("3794" in event.get("full_text", "") for event in events)


def test_route_clarifies_unknown_object_without_capture(chat_route):
    send, state = chat_route
    events = send("你看一下", [{"type": "glance", "value": "当前屏幕"}])
    assert state["actions"] == []
    assert any(event.get("full_text") == "你想让我看什么？" for event in events)


def test_route_launches_game_before_starting_requested_companionship(chat_route):
    send, state = chat_route
    send("来把大乱斗，你陪我打", [{"type": "play", "value": "英雄联盟"}, {"type": "glance", "value": "陪看 这局"}])
    assert state["actions"] == [("play", "英雄联盟"), ("vision", "陪看 这局")]


def test_route_only_playing_does_not_start_vision(chat_route):
    send, state = chat_route
    send("来把大乱斗", [{"type": "play", "value": "英雄联盟"}])
    assert state["actions"] == [("play", "英雄联盟")]


def test_route_single_look_captures_once_without_game_launch(chat_route):
    send, state = chat_route
    send("瞅瞅屏幕上这个报错", [{"type": "glance", "value": "这个报错"}])
    assert state["actions"] == [("vision", "这个报错")]
    assert len(state["captures"]) == 1


def test_route_unavailable_vision_reports_status_without_capture(chat_route):
    send, state = chat_route
    state["visual_result"] = "这台机器尚未配置视觉环境"
    send("看看屏幕上的报错", [{"type": "glance", "value": "这个报错"}])
    assert state["captures"] == []
    assert any("宿主事件：视觉状态" in text for text in state["calls"])


def test_route_stop_does_not_capture_or_say_looking(chat_route):
    send, state = chat_route
    state["visual_result"] = "closed"
    events = send("把眼睛关掉", [{"type": "glance", "value": "关闭"}])
    assert state["captures"] == []
    assert not any("我看看" in event.get("delta", "") for event in events)


@pytest.mark.parametrize("extra", [{"mode": "welcome"}, {"reroll": True}])
def test_non_user_events_cannot_authorize_new_vision_or_game_actions(chat_route, extra):
    send, state = chat_route
    send("看看屏幕，开英雄联盟", [{"type": "glance", "value": "陪看 当前屏幕"}, {"type": "play", "value": "英雄联盟"}], **extra)
    assert state["actions"] == []
    assert state["captures"] == []


def test_together_watch_responds_once_without_waiting_for_model_or_second_capture(chat_route, monkeypatch):
    send, state = chat_route
    registered = []
    monkeypatch.setattr(along, "register_opening", lambda text, cid: registered.append((text, cid)))
    events = send("一起看", [{"type": "text", "delta": "我看看。我看看。"}])
    spoken = "".join(event.get("delta", "") for event in events if event["type"] == "text")
    assert spoken == "好呀，我陪你一起看。"
    assert state["calls"] == []
    assert state["actions"] == [("vision", "陪看 一起看")]
    assert state["captures"] == []
    assert registered == [(spoken, 1)]


def test_fragmented_model_preface_is_not_repeated_by_host(chat_route):
    send, _ = chat_route
    events = send("瞅瞅屏幕上这个报错", [
        {"type": "text", "delta": "我"}, {"type": "text", "delta": "看"},
        {"type": "text", "delta": "看。"}, {"type": "glance", "value": "这个报错"},
    ])
    spoken = "".join(e.get("delta", "") for e in events if e["type"] == "text")
    assert spoken.count("我看看") == 1


def test_watch_command_is_applied_only_in_user_turns(chat_route, monkeypatch):
    send, state = chat_route
    controls = []
    monkeypatch.setattr(along, "configure", lambda value, cid, user: controls.append((value, cid, user)) or {"ok": True})
    events = send("多说说话", [{"type": "watch", "value": '{"talk":"more"}'}, {"type": "text", "delta": "好，那我多跟你聊聊。"}])
    assert controls == [('{"talk":"more"}', 1, "多说说话")]
    assert state["actions"] == [] and state["captures"] == []
    assert any(e["type"] == "watch_status" and e["ok"] for e in events)
    send("多说说话", [{"type": "watch", "value": '{"talk":"quiet"}'}], mode="welcome")
    assert len(controls) == 1


def test_rejected_watch_command_cannot_claim_success(chat_route, monkeypatch):
    send, state = chat_route
    monkeypatch.setattr(along, "configure", lambda *args: {"ok": False, "message": "当前没有开启陪看"})
    events = send("多说说话", [{"type": "watch", "value": '{"talk":"more"}'}, {"type": "text", "delta": "错误地说已经调整。"}])
    spoken = "".join(e.get("delta", "") for e in events if e["type"] == "text")
    assert "错误地说已经调整" not in spoken
    assert any("陪看要求未采用" in text for text in state["calls"])


def test_character_model_bypass_still_handles_explicit_visual_request(chat_route, monkeypatch):
    send, state = chat_route
    from app.modules.harness import service as harness_service
    from app.services import llm as llm_service
    from app.services import settings_store

    previous = settings_store.get_all
    monkeypatch.setattr(settings_store, "get_all", lambda session: {
        **previous(session),
        "modules": {**previous(session)["modules"], "glance": True},
    })
    monkeypatch.setattr(harness_service, "turn_uses_harness", lambda **kwargs: False)

    async def ordinary_model(_conf, messages):
        assert any("你正在玩英雄联盟" in str(item.get("content") or "") for item in messages)
        yield {"type": "text", "delta": "你在玩英雄联盟。"}
        yield {"type": "done", "full_text": "你在玩英雄联盟。"}

    monkeypatch.setattr(llm_service, "stream_chat", ordinary_model)
    events = send("看看我在干嘛？", [])
    assert state["actions"] == [("vision", "在干嘛")]
    assert state["captures"]
    assert any(event.get("full_text") == "好，我看一眼。你在玩英雄联盟。" for event in events)


def test_character_model_status_chat_does_not_capture(chat_route, monkeypatch):
    send, state = chat_route
    from app.modules.harness import service as harness_service
    from app.services import llm as llm_service
    from app.services import settings_store

    previous = settings_store.get_all
    monkeypatch.setattr(settings_store, "get_all", lambda session: {
        **previous(session),
        "modules": {**previous(session)["modules"], "glance": True},
    })
    monkeypatch.setattr(harness_service, "turn_uses_harness", lambda **kwargs: False)

    async def ordinary_model(_conf, _messages):
        yield {"type": "glance", "value": "在干嘛"}
        yield {"type": "text", "delta": "我在陪你聊天呢。"}
        yield {"type": "done", "full_text": "我在陪你聊天呢。"}

    monkeypatch.setattr(llm_service, "stream_chat", ordinary_model)
    events = send("你在干嘛呢？", [])

    assert state["actions"] == []
    assert state["captures"] == []
    assert any(event.get("full_text") == "我在陪你聊天呢。" for event in events)
