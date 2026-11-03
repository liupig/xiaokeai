"""Turn ownership, interruption and continuity regressions. No remote model calls."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.modules.harness import service, stream_tap
from app.modules.harness.memory import CONTEXT_BUDGET, continuity, read_state, write_state


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "home_dir", lambda: tmp_path)
    return tmp_path


class Harness:
    def __init__(self):
        self.prompts = []
        self.closed = False
        self.resume = []

    def resume_session(self, sid):
        self.resume.append(sid)
        raise RuntimeError(f"session {sid} not found")

    def start_session(self, sid):
        self.sid = sid
        return self

    def run(self, prompt, on_notification):
        self.prompts.append((self.sid, prompt))
        return SimpleNamespace(finish_reason="end_turn", final_response="你好。", events=[])

    def close(self):
        self.closed = True


def args(**overrides):
    return dict(character_id=1, user_text="你好", brief="【稳定身份】\n你是清宵。\n\n【动态现场】\n现在是早上。",
                prior=[], on_delta=lambda _: None, **overrides)


def setup_runtime(monkeypatch, harness=None):
    instance = service.Runtime()
    harness = harness or Harness()
    monkeypatch.setattr(instance, "ensure", lambda _: harness)
    return instance, harness


def test_waiting_turn_cannot_subscribe_to_running_turn(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    listeners = []
    active_counts = []

    def subscribe(_base, fn):
        listeners.append(fn)
        return lambda: listeners.remove(fn)

    def run(prompt, on_notification):
        harness.prompts.append(prompt)
        active_counts.append(len(listeners))
        if len(harness.prompts) == 1:
            entered.set()
            assert release.wait(3)
        for listener in list(listeners):
            listener("甲。" if len(harness.prompts) == 1 else "乙。")
        return SimpleNamespace(finish_reason="end_turn", final_response="", events=[])

    monkeypatch.setattr(stream_tap, "subscribe_text", subscribe)
    harness.run = run
    first, second = [], []
    with ThreadPoolExecutor(2) as pool:
        a = args(); a["on_delta"] = first.append
        one = pool.submit(instance.run_turn, {}, **a)
        assert entered.wait(3)
        b = args(); b["on_delta"] = second.append
        two = pool.submit(instance.run_turn, {}, **b)
        release.set()
        one.result(3); two.result(3)
    assert first == ["甲。"]
    assert second == ["乙。"]
    assert active_counts == [1, 1]
    assert service._read_turns(1) == 2


def test_cancel_closes_only_own_turn_and_discards_its_session(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    entered, closed = threading.Event(), threading.Event()
    cancel = threading.Event()

    def run(prompt, on_notification):
        entered.set()
        assert closed.wait(3)
        return SimpleNamespace(finish_reason="end_turn", final_response="不该播的尾巴。", events=[])

    harness.run = run
    harness.close = closed.set
    output = []
    with ThreadPoolExecutor(1) as pool:
        a = args(); a["on_delta"] = output.append
        job = pool.submit(instance.run_turn, {}, cancel=cancel, **a)
        assert entered.wait(3)
        instance.cancel_turn(threading.Event())
        assert not closed.is_set()
        instance.cancel_turn(cancel)
        with pytest.raises(service.TurnCancelled):
            job.result(3)
    assert output == []
    assert service.needs_seed(1)
    assert service._generation(1) == 1
    assert service._read_turns(1) == 0


def test_cancelled_waiter_does_not_run_or_rotate_active_session(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    token = threading.Event(); token.set()
    with pytest.raises(service.TurnCancelled):
        instance.run_turn({}, cancel=token, **args())
    assert harness.prompts == []
    assert service._generation(1) == 0


def test_persona_version_and_dynamic_scene_refresh(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    instance.run_turn({}, **args())
    a = args(); a["brief"] = a["brief"].replace("早上", "晚上")
    instance.run_turn({}, **a)
    assert "你是清宵" not in harness.prompts[-1][1]
    assert "现在是晚上" in harness.prompts[-1][1]
    a["brief"] = a["brief"].replace("清宵", "小雨")
    instance.run_turn({}, **a)
    assert "你是小雨" in harness.prompts[-1][1]
    assert harness.prompts[-1][0] != harness.prompts[-2][0]


def test_token_budget_rotates_and_carries_verbatim_continuity(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    instance.run_turn({}, **args())
    path = isolated / "xiaoke-seed/1.context.json"
    state = read_state(path); state["tokens"] = CONTEXT_BUDGET
    write_state(path, state)
    a = args(); a["prior"] = [{"role": "user", "content": "记住，我喜欢猫。"}]
    instance.run_turn({}, **a)
    assert harness.prompts[-1][0] != harness.prompts[-2][0]
    assert "【延续记忆】" in harness.prompts[-1][1]
    assert "我喜欢猫" in harness.prompts[-1][1]
    state = read_state(path)
    assert 0 < state["tokens"] < CONTEXT_BUDGET
    for i in range(30):
        continuity(state, [{"role": "user", "content": f"我喜欢第{i}种花"}])
    assert len(state["preferences"]) == 8


def test_key_rotation_and_removal_are_applied(monkeypatch, isolated):
    import deepseek_harness
    made = []
    def create(**kwargs):
        harness = Harness(); made.append((kwargs, harness)); return harness
    monkeypatch.setattr(deepseek_harness, "DeepSeekHarness", create)
    monkeypatch.setattr(service, "glance_on", lambda: False)
    monkeypatch.setattr(service, "process_cwd", lambda _: None)
    instance = service.Runtime()
    instance.ensure({"api_key": "first"})
    instance.ensure({"api_key": "second"})
    assert len(made) == 2
    assert made[0][1].closed
    assert made[1][0]["api_key"] == "second"
    assert "second" not in repr(instance._launch)
    with pytest.raises(service.HarnessError):
        instance.ensure({"api_key": ""})


@pytest.mark.parametrize("termination", ["close", "timeout", "invalid"])
def test_async_consumer_termination_cancels_worker(monkeypatch, termination):
    entered, cancelled, done = threading.Event(), threading.Event(), threading.Event()
    def run_turn(_conf, **kwargs):
        entered.set()
        kwargs["on_delta"]("开头。")
        assert cancelled.wait(3)
        done.set()
    def cancel_turn(token):
        token.set(); cancelled.set()
    monkeypatch.setattr(service, "runtime", lambda: SimpleNamespace(run_turn=run_turn, cancel_turn=cancel_turn))
    async def consume():
        valid = [True]
        stream = service.stream_reply({}, character_id=1, user_text="你好", brief="",
            timeout=0.15 if termination == "timeout" else 3, valid=lambda: valid[0])
        first = await anext(stream)
        assert first["type"] == "text"
        if termination == "close":
            await stream.aclose()
        else:
            valid[0] = termination != "invalid"
            rest = [event async for event in stream]
            if termination == "timeout":
                assert rest[-1]["code"] == "harness_timeout"
            else:
                assert rest == []
    asyncio.run(consume())
    assert entered.is_set() and cancelled.is_set()
    assert done.wait(3)


def test_utf8_stream_can_split_at_every_byte():
    parser = stream_tap.SseTextTap()
    raw = ('data: ' + json.dumps({"type": "content_block_delta", "delta": {
        "type": "text_delta", "text": "你好，清宵🌙。"}}, ensure_ascii=False) + '\n\n').encode()
    assert "".join(text for byte in raw for text in parser.feed(bytes([byte]))) == "你好，清宵🌙。"


def test_old_http_response_cannot_publish_to_next_subscriber(monkeypatch):
    import httpx
    async def run():
        first, release = asyncio.Event(), asyncio.Event()
        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"old"}}\n\n'
                first.set()
                await release.wait()
                yield b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"tail"}}\n\n'
        class Writer:
            def write(self, data):
                pass
            async def drain(self):
                pass
        transport = httpx.MockTransport(lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Body()))
        client = httpx.AsyncClient(transport=transport)
        monkeypatch.setattr(stream_tap.httpx, "AsyncClient", lambda **_: client)
        tap = stream_tap.MessagesTap("http://local.test")
        old, new = [], []
        off = tap.subscribe(old.append)
        relay = asyncio.create_task(tap._relay(Writer(), "POST", "/v1/messages", {}, b"{}"))
        await asyncio.wait_for(first.wait(), 2)
        off(); tap.subscribe(new.append)
        release.set()
        await relay
        assert old == ["old"]
        assert new == []
    asyncio.run(run())


def test_chat_forwarding_drops_only_runtime_metadata():
    obj = {"dsh_session_log": {"events": ["coding log"]}, "dsh_plugin_packages": {"packages": ["inventory"]},
           "messages": [{"role": "user", "content": "hello"}], "system": "persona",
           "tools": [{"name": "skill"}], "thinking": {"type": "enabled", "budget_tokens": 1024}}
    result = json.loads(stream_tap.chat_body(json.dumps(obj).encode()))
    assert result == {key: value for key, value in obj.items() if not key.startswith("dsh_")}
    assert stream_tap.chat_body(b"not JSON") == b"not JSON"


def test_proxy_reuses_upstream_connection_and_keeps_request_credentials():
    import httpx
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    seen = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *args):
            pass
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            seen.append((self.client_address[1], self.headers.get("x-api-key")))
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        local = stream_tap.tap_base(f"http://127.0.0.1:{server.server_port}")
        with httpx.Client(trust_env=False, timeout=3) as client:
            for key in ("test-first", "test-second"):
                response = client.post(local + "/v1/messages", json={}, headers={"x-api-key": key})
                assert response.status_code == 200
        assert [item[1] for item in seen] == ["test-first", "test-second"]
        assert seen[0][0] == seen[1][0]
    finally:
        server.shutdown(); server.server_close(); thread.join(3)


def test_warmup_starts_runtime_without_sending_model_prompt(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    started = threading.Event()
    harness.start = started.set
    monkeypatch.setattr(service, "runtime", lambda: instance)
    service.schedule_warmup({"llm": {"api_key": "test-dummy", "model": "test"}})
    assert started.wait(2)
    assert harness.prompts == []
    instance.close()


def test_warmup_is_interruptible_while_starting(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    started, stopped = threading.Event(), threading.Event()
    def start():
        started.set()
        assert stopped.wait(3)
    harness.start = start
    harness.close = stopped.set
    with ThreadPoolExecutor(1) as pool:
        job = pool.submit(instance.warmup, {})
        assert started.wait(2)
        instance.close()
        job.result(2)
    assert stopped.is_set()


def test_disabled_harness_does_not_warm_up(monkeypatch):
    def forbidden():
        raise AssertionError("disabled module must not create a runtime")
    monkeypatch.setattr(service, "runtime", forbidden)
    service.schedule_warmup({"modules": {"harness": False}, "llm": {"api_key": "test-dummy"}})


def test_cancel_after_generation_is_persisted_across_runtime_restart(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    token = threading.Event()
    instance.run_turn({}, cancel=token, **args())
    old_sid = harness.prompts[-1][0]
    instance.cancel_turn(token)
    replacement, new_harness = setup_runtime(monkeypatch)
    replacement.run_turn({}, **args())
    assert new_harness.prompts[-1][0] != old_sid


def test_grounded_repair_uses_injected_agent_and_preserves_checks(monkeypatch):
    from app.modules.glance.game_director import grounded_reply
    from app.services import llm
    def forbidden(*args, **kwargs):
        raise AssertionError("must not use a separate chat model")
    monkeypatch.setattr(llm, "stream_chat", forbidden)
    calls = []
    async def agent(conf, messages):
        calls.append(list(messages))
        yield {"type": "text", "delta": "你五杀了！" if len(calls) == 1 else "这一下真紧张。"}
        yield {"type": "done", "full_text": ""}
    result = asyncio.run(grounded_reply({}, [{"role": "user", "content": "接一句"}],
        evidence="正在交战", topic="game", stream=agent))
    assert len(calls) == 2
    assert "没有依据" in calls[1][-1]["content"]
    assert result["action"] == "speak"
    assert result["text"] == "这一下真紧张。"


def test_spoken_gate_keeps_ordinary_skill_discussion():
    from app.modules.harness.brief import SpokenGate
    assert SpokenGate().feed("我想学一项新技能。") == "我想学一项新技能。"


def test_correction_discards_old_agent_history_and_continuity(monkeypatch, isolated):
    instance, harness = setup_runtime(monkeypatch)
    monkeypatch.setattr(service, "runtime", lambda: instance)
    instance.run_turn({}, **args())
    service.invalidate_history(1)
    assert service.needs_seed(1)
    assert not (isolated / "xiaoke-seed/1.context.json").exists()


def test_chat_profile_has_only_skill_tool_with_real_runtime(tmp_path, monkeypatch):
    """Boot the installed native runtime against a local fake Messages server."""
    sdk = pytest.importorskip("deepseek_harness")
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append([tool["name"] for tool in body.get("tools", [])])
            events = [
                {"type": "message_start", "message": {"id": "msg_test", "type": "message", "role": "assistant",
                 "model": "deepseek-v4-flash", "content": [], "stop_reason": None, "stop_sequence": None,
                 "usage": {"input_tokens": 10, "output_tokens": 0}}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "你好。"}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 3}},
                {"type": "message_stop"},
            ]
            data = "".join("event: " + event["type"] + "\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in events).encode()
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    service.sync_skills(tmp_path)
    harness = sdk.DeepSeekHarness(dsh_home=str(tmp_path), cwd=str(tmp_path / "workspace"),
        runtime_cwd=service.process_cwd(tmp_path / "workspace"), profile="sdk", api_key="test-dummy",
        base_url=f"http://127.0.0.1:{server.server_port}", initialize_timeout_seconds=40, request_timeout_seconds=10)
    try:
        result = harness.run("你好", session_id="tool-check")
        assert seen and all(names == ["skill"] for names in seen)
        assert result.finish_reason != "error", service._turn_error(result.events)
        assert result.final_response == "你好。"
    finally:
        harness.close()
    instance = service.Runtime()
    monkeypatch.setattr(service, "home_dir", lambda: tmp_path)
    monkeypatch.setattr(service, "glance_on", lambda: False)
    monkeypatch.setattr(service, "runtime", lambda: instance)
    async def through_host_pipeline():
        return [event async for event in service.stream_reply(
            {"api_key": "test-dummy", "base_url": f"http://127.0.0.1:{server.server_port}", "thinking": "off"},
            character_id=1, user_text="你好", brief="你是清宵。", timeout=15)]
    try:
        events = asyncio.run(through_host_pipeline())
        assert not [event for event in events if event["type"] == "error"]
        assert "".join(event.get("delta", "") for event in events if event["type"] == "text") == "你好。"
        assert events[-1] == {"type": "done", "full_text": "你好。"}
        assert all(names == ["skill"] for names in seen)
    finally:
        instance.close(); server.shutdown(); server.server_close(); thread.join(3)
