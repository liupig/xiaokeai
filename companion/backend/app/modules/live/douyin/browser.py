"""用本机浏览器打开公开直播间，收它自己连上的弹幕。

签名在直播页里算。这里不拷那份脚本，只看这个页面已经收到的推送。
无头窗口会被直播页跳过弹幕通道，所以默认开一个普通窗口。
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Callable

import httpx
from websocket import create_connection

from .messages import events_from_body, unpack_push

_CHROME = (
    os.environ.get("COMPANION_CHROME", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def browser_path() -> str:
    for path in _CHROME:
        if path and os.path.isfile(path):
            return path
    raise RuntimeError("没有找到 Chrome 或 Edge，打不开直播间")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _page_socket(port: int, deadline: float) -> str:
    url = f"http://127.0.0.1:{port}/json/list"
    while time.time() < deadline:
        try:
            rows = httpx.get(url, timeout=1).json()
        except Exception:
            time.sleep(0.2)
            continue
        for row in rows:
            if row.get("type") == "page" and row.get("webSocketDebuggerUrl"):
                return str(row["webSocketDebuggerUrl"])
        time.sleep(0.2)
    raise RuntimeError("浏览器调试口没有起来")


class _Viewer:
    def __init__(self, room_url: str, headless: bool) -> None:
        self.room_url = room_url
        self.headless = headless
        self.proc: subprocess.Popen | None = None
        self.profile = ""
        self.ws = None
        self._next = 0
        self.sockets: dict[str, str] = {}
        self.fetch_ids: set[str] = set()
        self.body_wait: dict[int, str] = {}
        self.connected = False

    def open(self) -> None:
        port = _free_port()
        self.profile = tempfile.mkdtemp(prefix="xiaoke-douyin-")
        cmd = [
            browser_path(),
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-sync",
            "--mute-audio",
            "--window-size=1100,720",
            "--window-position=60,60",
            "--autoplay-policy=no-user-gesture-required",
            "about:blank",
        ]
        if self.headless:
            cmd.insert(1, "--headless=new")
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        page = _page_socket(port, time.time() + 12)
        self.ws = create_connection(page, timeout=8, suppress_origin=True)
        self.ws.settimeout(1)
        self._call("Network.enable")
        self._call("Page.enable")
        self._call("Page.navigate", {"url": self.room_url})

    def _call(self, method: str, params: dict | None = None) -> int:
        self._next += 1
        msg = {"id": self._next, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        return self._next

    def pump(self, on_events: Callable[[list[dict]], None], stop, until: float) -> None:
        while time.time() < until and not stop.is_set():
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError("浏览器关了，弹幕断开了")
            try:
                raw = self.ws.recv()
            except Exception:
                continue
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            self._on_cdp(msg, on_events)

    def _on_cdp(self, msg: dict, on_events: Callable[[list[dict]], None]) -> None:
        call_id = msg.get("id")
        if call_id in self.body_wait:
            self.body_wait.pop(call_id, None)
            self._take_fetch(msg.get("result") or {}, on_events)
            return
        method = msg.get("method") or ""
        params = msg.get("params") or {}
        if method == "Network.webSocketCreated":
            self.sockets[str(params.get("requestId") or "")] = str(params.get("url") or "")
            return
        if method == "Network.responseReceived":
            url = str((params.get("response") or {}).get("url") or "")
            if "/webcast/im/fetch/" in url:
                self.fetch_ids.add(str(params.get("requestId") or ""))
            return
        if method == "Network.loadingFinished":
            request_id = str(params.get("requestId") or "")
            if request_id in self.fetch_ids:
                self.fetch_ids.discard(request_id)
                call_id = self._call("Network.getResponseBody", {"requestId": request_id})
                self.body_wait[call_id] = request_id
            return
        if method != "Network.webSocketFrameReceived":
            return
        request_id = str(params.get("requestId") or "")
        url = self.sockets.get(request_id, "")
        if "webcast" not in url or "/im/" not in url:
            return
        frame = params.get("response") or {}
        payload = frame.get("payloadData") or ""
        if not payload:
            return
        try:
            if int(frame.get("opcode") or 0) == 1:
                data = payload.encode("utf-8", "surrogateescape")
            else:
                data = base64.b64decode(payload)
            events, _ack = unpack_push(data)
        except Exception:
            return
        self.connected = True
        if events:
            on_events(events)

    def _take_fetch(self, result: dict, on_events: Callable[[list[dict]], None]) -> None:
        if result.get("error") or not result.get("body"):
            return
        try:
            body = result.get("body") or ""
            data = base64.b64decode(body) if result.get("base64Encoded") else body.encode("utf-8", "surrogateescape")
            events, _cursor, _internal = events_from_body(data)
        except Exception:
            return
        self.connected = True
        if events:
            on_events(events)

    def close(self) -> None:
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass
        self.ws = None
        proc = self.proc
        self.proc = None
        if proc is not None and proc.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        if self.profile:
            shutil.rmtree(self.profile, ignore_errors=True)
            self.profile = ""


def watch(room_url: str, on_events: Callable[[list[dict]], None], stop, *,
         headless: bool = False, on_ready: Callable[[], None] | None = None) -> None:
    """阻塞到 stop，或直播页一直没有弹幕通道。"""
    viewer = _Viewer(room_url, headless)
    ready = False
    try:
        viewer.open()
        quiet_until = time.time() + 25
        while not stop.is_set():
            viewer.pump(on_events, stop, time.time() + 1)
            if viewer.connected:
                if not ready and on_ready is not None:
                    on_ready()
                ready = True
                quiet_until = time.time() + 30
                continue
            if time.time() > quiet_until:
                raise RuntimeError("直播间页面没有连上弹幕。确认这间正在播，并且浏览器里能打开这个链接")
    finally:
        viewer.close()
