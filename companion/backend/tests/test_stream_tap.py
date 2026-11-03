"""Messages 流在整段结束前就把正文交出来。不连真的模型。"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.harness.brief import TextGrowth  # noqa: E402
from app.modules.harness.stream_tap import (  # noqa: E402
    SseTextTap,
    slim_xiaomi_body,
    text_delta_from_sse_line,
    tap_base,
    subscribe_text,
)


def test_only_spoken_text_deltas_count():
    line = (
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"在呢"}}'
    )
    assert text_delta_from_sse_line(line) == "在呢"
    thinking = (
        'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"先想"}}'
    )
    assert text_delta_from_sse_line(thinking) == ""
    tool = (
        'data: {"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{\\"q\\":"}}'
    )
    assert text_delta_from_sse_line(tool) == ""
    assert text_delta_from_sse_line("data: [DONE]") == ""


def test_sse_lines_can_split_across_packets():
    tap = SseTextTap()
    raw = (
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"你"}}\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"好"}}\n'
    ).encode()
    assert tap.feed(raw[:20]) == []
    assert "".join(tap.feed(raw[20:])) == "你好"


def test_text_arrives_before_the_upstream_finishes():
    pieces = ["在呢", "，宝。"]

    async def upstream(reader, writer):
        header = await reader.readuntil(b"\r\n\r\n")
        if b"content-length:" in header.lower():
            for line in header.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    await reader.readexactly(int(line.split(b":", 1)[1].strip() or b"0"))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n")
        await writer.drain()
        for piece in pieces:
            payload = (
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"%s"}}\n\n'
                % piece
            ).encode()
            writer.write(payload)
            await writer.drain()
            await asyncio.sleep(0.35)
        writer.write(b"data: {\"type\":\"message_stop\"}\n\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    loop = asyncio.new_event_loop()

    def serve():
        asyncio.set_event_loop(loop)
        server = loop.run_until_complete(asyncio.start_server(upstream, "127.0.0.1", 0))
        sock = server.sockets[0]
        serve.port = sock.getsockname()[1]
        serve.ready.set()
        loop.run_until_complete(server.serve_forever())

    serve.ready = threading.Event()
    serve.port = 0
    threading.Thread(target=serve, daemon=True).start()
    assert serve.ready.wait(5)
    upstream_base = f"http://127.0.0.1:{serve.port}/anthropic"
    local = tap_base(upstream_base)
    got: list[tuple[float, str]] = []
    t0 = time.perf_counter()

    def on_text(text: str) -> None:
        got.append((time.perf_counter() - t0, text))

    subscribe_text(upstream_base, on_text)
    with httpx.Client(timeout=10, trust_env=False) as client:
        with client.stream(
            "POST",
            local + "/v1/messages",
            json={"messages": [{"role": "user", "content": "hi"}]},
        ) as resp:
            assert resp.status_code == 200
            body = b"".join(resp.iter_bytes())
    assert "在呢" in body.decode()
    assert [text for _at, text in got] == pieces
    assert got[-1][0] > got[0][0] + 0.2
    growth = TextGrowth()
    for _at, text in got:
        growth.feed({
            "type": "assistant/chunk",
            "data": {"chunk": {"type": "text-delta", "text": text}},
        })
    assert growth.feed({
        "type": "assistant/message",
        "data": {"message": {"content": [{"type": "text", "text": "在呢，宝。"}]}},
    }) == ""


def test_xiaomi_chat_drops_the_agent_manual():
    raw = json.dumps({
        "thinking": {"type": "disabled"},
        "system": "先开口。\n\nNon-zero exits are reported.",
        "tools": [
            {"name": "pwsh", "description": "shell"},
            {"name": "skill", "description": "dance"},
        ],
        "dsh_session_log": {"events": []},
        "dsh_plugin_packages": {"packages": []},
        "messages": [{"role": "user", "content": "在吗"}],
    }, ensure_ascii=False).encode()
    obj = json.loads(slim_xiaomi_body(raw))
    assert "Non-zero" not in obj["system"]
    assert obj["system"].startswith("先开口")
    assert [tool["name"] for tool in obj["tools"]] == ["skill"]
    assert "dsh_session_log" not in obj
    assert "dsh_plugin_packages" not in obj
    assert obj["enable_thinking"] is False
    kept = json.loads(slim_xiaomi_body(json.dumps({
        "thinking": {"type": "enabled"},
        "system": "Non-zero exits",
        "tools": [{"name": "pwsh"}],
    }).encode()))
    assert kept["tools"][0]["name"] == "pwsh"
    assert "enable_thinking" not in kept
    replay = json.loads(slim_xiaomi_body(json.dumps({
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "先写计划"},
                {"type": "text", "text": "在呢"},
            ]},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "只有计划"},
            ]},
        ],
    }, ensure_ascii=False).encode()))
    assert replay["messages"] == [
        {"role": "assistant", "content": [{"type": "text", "text": "在呢"}]},
    ]
