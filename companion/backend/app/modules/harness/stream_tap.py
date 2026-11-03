"""dsh 要等整段 assistant/message 落盘才通知宿主。

这里在 Messages 前面接一层本地转发。text_delta 一到就交给当前这一轮，
第一句可以先开口，后面的字还在往下长。
"""
from __future__ import annotations

import asyncio
import codecs
import json
import threading
from contextlib import asynccontextmanager
from typing import Callable
from urllib.parse import urlsplit

import httpx

_HOP = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
    "accept-encoding",
    "keep-alive",
    "proxy-connection",
    "te",
    "trailer",
    "upgrade",
}


# dsh 接在系统提示后面的编程手册。小米看到这段就会先写英文计划。
_AGENT_TAIL = "Non-zero exits"
# 跳舞还要 skill。改文件、跑命令、列计划这些会把闲聊变成代理。
_CHAT_TOOLS = frozenset({"skill"})


_THINKING_BLOCKS = frozenset({"thinking", "reasoning", "redacted_thinking"})


def chat_body(body: bytes) -> bytes:
    """Conversation messages already carry the context needed for chat.

    Coding runtime inventory and raw persistence events are not part of the
    third-party Messages contract. Keep actual messages, thinking and tools.
    """
    try:
        obj = json.loads(body)
    except (UnicodeError, ValueError):
        return body
    if not isinstance(obj, dict):
        return body
    removed = False
    for key in ("dsh_plugin_packages", "dsh_session_log"):
        if key in obj:
            del obj[key]
            removed = True
    return json.dumps(obj, ensure_ascii=False).encode("utf-8") if removed else body


def _drop_replayed_thinking(messages: object) -> int:
    """上一轮的思考块再送回去，小米会接着写计划，一句短话也能拖很久。"""
    if not isinstance(messages, list):
        return 0
    dropped = 0
    kept: list[object] = []
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "assistant":
            content = message.get("content")
            if isinstance(content, list):
                spoken = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") in _THINKING_BLOCKS:
                        dropped += 1
                        continue
                    spoken.append(block)
                if not spoken:
                    continue
                message["content"] = spoken
        kept.append(message)
    messages[:] = kept
    return dropped


def _cut_agent_manual(text: str) -> str:
    if _AGENT_TAIL not in text:
        return text
    return text.split(_AGENT_TAIL, 1)[0].rstrip()


def slim_xiaomi_body(body: bytes) -> bytes:
    """关思考时别把编程代理的会话和工具一并发给小米。

    思考开关已经是 disabled，它仍会先写计划：会话日志和那一串
    create_goal / exit_plan_mode 让它以为自己在做代理。计划占满
    max_tokens 之后，要说的话就没了。
    """
    try:
        obj = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return body
    if not isinstance(obj, dict):
        return body
    thinking = obj.get("thinking")
    if not (isinstance(thinking, dict) and thinking.get("type") == "disabled"):
        return body
    obj.pop("dsh_plugin_packages", None)
    obj.pop("dsh_session_log", None)
    # thinking.type=disabled 挡不住。小米还认这个开关，带上才不会先写计划。
    obj["enable_thinking"] = False
    _drop_replayed_thinking(obj.get("messages"))
    system = obj.get("system")
    if isinstance(system, str):
        obj["system"] = _cut_agent_manual(system)
    elif isinstance(system, list):
        kept = []
        for block in system:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                text = _cut_agent_manual(block["text"])
                if not text:
                    continue
                block = {**block, "text": text}
            kept.append(block)
        obj["system"] = kept
    tools = obj.get("tools")
    if isinstance(tools, list):
        chat_tools = [
            tool for tool in tools
            if isinstance(tool, dict) and tool.get("name") in _CHAT_TOOLS
        ]
        obj["tools"] = chat_tools
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def text_delta_from_sse_line(line: str) -> str:
    """Anthropic 的 text_delta。思考和工具参数不算要念的话。"""
    raw = (line or "").strip()
    if not raw or raw.startswith(":"):
        return ""
    if raw.startswith("data:"):
        raw = raw[5:].strip()
    if not raw or raw == "[DONE]":
        return ""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(obj, dict):
        return ""
    if obj.get("type") == "content_block_delta":
        delta = obj.get("delta") if isinstance(obj.get("delta"), dict) else {}
        if delta.get("type") == "text_delta":
            return str(delta.get("text") or "")
        return ""
    choices = obj.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        delta = choices[0].get("delta") if isinstance(choices[0].get("delta"), dict) else {}
        return str(delta.get("content") or "")
    return ""


async def _read_chunked(reader: asyncio.StreamReader) -> bytes:
    out = bytearray()
    while True:
        line = await reader.readuntil(b"\r\n")
        size = int(line.strip().split(b";", 1)[0] or b"0", 16)
        if size == 0:
            while True:
                extra = await reader.readuntil(b"\r\n")
                if extra in (b"\r\n", b""):
                    break
            return bytes(out)
        out += await reader.readexactly(size)
        await reader.readexactly(2)


class SseTextTap:
    """跨 TCP 分片把 SSE 行拆开，只交出新增正文。"""

    def __init__(self) -> None:
        self._buf = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def feed(self, data: bytes) -> list[str]:
        self._buf += self._decoder.decode(data)
        found: list[str] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            text = text_delta_from_sse_line(line)
            if text:
                found.append(text)
        return found


class MessagesTap:
    def __init__(self, upstream: str) -> None:
        parsed = urlsplit(upstream.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"无法转发的地址：{upstream}")
        self.upstream = upstream.rstrip("/")
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.path = parsed.path.rstrip("/")
        self.port = 0
        self.local_base = ""
        self._listeners: list[Callable[[str], None]] = []
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._http: httpx.AsyncClient | None = None

    def start(self) -> str:
        if self.local_base:
            return self.local_base
        self._thread = threading.Thread(target=self._run, name="llm-stream-tap", daemon=True)
        self._thread.start()
        if not self._ready.wait(8):
            raise TimeoutError("本地流式转发没有听上端口")
        if self._error is not None:
            raise self._error
        return self.local_base

    def subscribe(self, callback: Callable[[str], None]) -> Callable[[], None]:
        active = threading.Event()
        active.set()

        def listener(text: str) -> None:
            if active.is_set():
                callback(text)

        with self._lock:
            self._listeners.append(listener)

        def off() -> None:
            active.clear()
            with self._lock:
                try:
                    self._listeners.remove(listener)
                except ValueError:
                    pass

        return off

    def emit(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(text)
            except Exception:
                pass

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._serve())
        except Exception as exc:
            self._error = exc
            self._ready.set()

    async def _serve(self) -> None:
        server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        sock = server.sockets[0]
        self.port = int(sock.getsockname()[1])
        self.local_base = f"http://127.0.0.1:{self.port}{self.path}"
        self._ready.set()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180, connect=15), trust_env=False,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4, keepalive_expiry=60),
        ) as client:
            self._http = client
            try:
                async with server:
                    await server.serve_forever()
            finally:
                self._http = None

    @asynccontextmanager
    async def _upstream_client(self):
        if self._http is not None:
            yield self._http
        else:
            # Direct relay tests do not run the server lifecycle.
            async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15), trust_env=False) as client:
                yield client

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 30)
            head, _sep, _rest = header.partition(b"\r\n\r\n")
            lines = head.decode("iso-8859-1").split("\r\n")
            method, target, _version = lines[0].split(" ", 2)
            headers: dict[str, str] = {}
            for line in lines[1:]:
                if ":" not in line:
                    continue
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()
            if "chunked" in headers.get("transfer-encoding", "").lower():
                body = await _read_chunked(reader)
            else:
                length = int(headers.get("content-length") or "0")
                body = await reader.readexactly(length) if length else b""
            await self._relay(writer, method, target, headers, body)
        except Exception as exc:
            try:
                msg = f"流式转发失败：{exc}".encode("utf-8", "replace")
                writer.write(
                    b"HTTP/1.1 502 Bad Gateway\r\n"
                    b"Content-Type: text/plain; charset=utf-8\r\n"
                    b"Connection: close\r\n"
                    + f"Content-Length: {len(msg)}\r\n\r\n".encode()
                    + msg
                )
                await writer.drain()
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _relay(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        target: str,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        # Bind this HTTP request to its turn. A cancelled response may still be
        # draining when the next turn subscribes; never broadcast it to that turn.
        with self._lock:
            listeners = list(self._listeners)
        fwd = {k: v for k, v in headers.items() if k not in _HOP}
        url = self.origin + target
        body = chat_body(body)
        if "xiaomimimo.com" in self.origin:
            body = slim_xiaomi_body(body)
            # User-Agent 里带着 deepseek-harness 时，小米会把思考重新打开。
            fwd.pop("user-agent", None)
            for name in [key for key in fwd if key.startswith("x-deepseek-harness-")]:
                fwd.pop(name, None)
        async with self._upstream_client() as client:
            async with client.stream(method, url, headers=fwd, content=body) as resp:
                ctype = resp.headers.get("content-type") or "application/octet-stream"
                reason = resp.reason_phrase or "OK"
                writer.write(
                    f"HTTP/1.1 {resp.status_code} {reason}\r\n".encode("ascii", "replace")
                )
                writer.write(f"Content-Type: {ctype}\r\n".encode("ascii", "replace"))
                writer.write(b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n")
                parser = SseTextTap() if "text/event-stream" in ctype.lower() else None
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    if parser is not None:
                        for text in parser.feed(chunk):
                            for listener in listeners:
                                listener(text)
                    writer.write(f"{len(chunk):X}\r\n".encode("ascii") + chunk + b"\r\n")
                    await writer.drain()
                writer.write(b"0\r\n\r\n")
                await writer.drain()


_TAPS: dict[str, MessagesTap] = {}
_TAP_LOCK = threading.Lock()


def tap_base(upstream: str | None) -> str | None:
    """dsh 用的地址。上流仍是原来的 Messages 口，中间多一跳只为拆字。"""
    if not upstream:
        return None
    key = upstream.rstrip("/")
    with _TAP_LOCK:
        tap = _TAPS.get(key)
        if tap is None:
            tap = MessagesTap(key)
            tap.start()
            _TAPS[key] = tap
        return tap.local_base


def subscribe_text(upstream: str | None, callback: Callable[[str], None]) -> Callable[[], None]:
    if not upstream:
        return lambda: None
    with _TAP_LOCK:
        tap = _TAPS.get(upstream.rstrip("/"))
    if tap is None:
        return lambda: None
    return tap.subscribe(callback)
