"""哔哩哔哩直播开放平台。身份码换长连接，不走网页房间。"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

import httpx

from ..events import LiveEvent
from .packet import OP_AUTH, OP_HEARTBEAT, OP_NOTIFY, pack_packet, unpack_packets
from .parse import events_from_json
from .sign import signed_headers

OPEN_LIVE = "https://live-open.biliapi.com"
_OnEvent = Callable[[LiveEvent], None]
_OnStatus = Callable[[dict], None]


class OpenLiveSession:
    def __init__(self, access_key_id: str, access_key_secret: str, app_id: int, code: str,
                 on_event: _OnEvent, on_status: _OnStatus) -> None:
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.app_id = int(app_id)
        self.code = code
        self._on_event = on_event
        self._on_status = on_status
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._game_id = ""
        self.reconnects = 0
        self.state = "idle"
        self.error = ""
        self.anchor = ""
        self.room_id = ""

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "error": self.error,
            "anchor": self.anchor,
            "room_id": self.room_id,
            "reconnects": self.reconnects,
            "game_id": bool(self._game_id),
        }

    def start(self) -> None:
        self.stop()
        self._stop = threading.Event()
        self.error = ""
        self.state = "connecting"
        self._emit()
        thread = threading.Thread(target=self._run, name="live-bili", daemon=True)
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=8)
        self._thread = None
        self._end_quiet()
        self.state = "idle"
        self._emit()

    def _emit(self) -> None:
        try:
            self._on_status(self.snapshot())
        except Exception:
            pass

    def _run(self) -> None:
        delay = 1
        while not self._stop.is_set():
            try:
                self._session_once()
                delay = 1
                if self._stop.is_set():
                    break
                raise RuntimeError("直播长连接断开")
            except Exception as exc:
                if self._stop.is_set():
                    break
                self.reconnects += 1
                self.error = str(exc)[:180]
                self.state = "down" if self.reconnects > 8 else "reconnecting"
                self._emit()
                self._end_quiet()
                if self.reconnects > 8:
                    break
                if self._stop.wait(delay):
                    break
                delay = min(delay * 2, 30)
        self.state = "idle" if self._stop.is_set() else self.state
        self._emit()

    def _session_once(self) -> None:
        import websocket

        info = self._api_start()
        self._game_id = info["game_id"]
        self.anchor = info.get("anchor") or ""
        self.room_id = str(info.get("room_id") or "")
        self.state = "live"
        self.error = ""
        self._emit()
        ws = websocket.create_connection(info["wss"], timeout=15, suppress_origin=True)
        try:
            ws.send(pack_packet(OP_AUTH, info["auth_body"].encode("utf-8")), opcode=0x2)
            ws.settimeout(1.0)
            last_hb = time.time()
            last_app = time.time()
            buf = b""
            while not self._stop.is_set():
                now = time.time()
                if now - last_hb >= 20:
                    ws.send(pack_packet(OP_HEARTBEAT, b""), opcode=0x2)
                    last_hb = now
                if now - last_app >= 20:
                    self._api_heartbeat()
                    last_app = now
                try:
                    chunk = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not chunk:
                    raise RuntimeError("直播长连接断开")
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                buf += chunk
                packets, buf = unpack_packets(buf)
                for op, body in packets:
                    if op == OP_NOTIFY:
                        for ev in events_from_json(body):
                            self._on_event(ev)
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = signed_headers(self.access_key_id, self.access_key_secret, body)
        with httpx.Client(timeout=httpx.Timeout(15, connect=8), trust_env=False) as client:
            resp = client.post(OPEN_LIVE + path, content=body, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"开放平台返回 {resp.status_code}")
        try:
            parsed = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("开放平台没有返回 JSON") from exc
        code = int(parsed.get("code") or 0)
        if code != 0:
            message = str(parsed.get("message") or parsed.get("msg") or "开放平台拒绝")
            raise RuntimeError(message[:180])
        data = parsed.get("data")
        return data if isinstance(data, dict) else {}

    def _api_start(self) -> dict:
        data = self._post("/v2/app/start", {"code": self.code, "app_id": self.app_id})
        game = data.get("game_info") if isinstance(data.get("game_info"), dict) else {}
        ws = data.get("websocket_info") if isinstance(data.get("websocket_info"), dict) else {}
        anchor = data.get("anchor_info") if isinstance(data.get("anchor_info"), dict) else {}
        links = ws.get("wss_link") if isinstance(ws.get("wss_link"), list) else []
        game_id = str(game.get("game_id") or "")
        auth_body = str(ws.get("auth_body") or "")
        wss = str(links[0] if links else "")
        if not game_id or not auth_body or not wss.startswith("wss://"):
            raise RuntimeError("开放平台没有给全长连接信息")
        return {
            "game_id": game_id,
            "auth_body": auth_body,
            "wss": wss,
            "anchor": str(anchor.get("uname") or ""),
            "room_id": str(anchor.get("room_id") or ""),
        }

    def _api_heartbeat(self) -> None:
        if self._game_id:
            self._post("/v2/app/heartbeat", {"game_id": self._game_id})

    def _end_quiet(self) -> None:
        game_id = self._game_id
        self._game_id = ""
        if not game_id:
            return
        try:
            self._post("/v2/app/end", {"game_id": game_id, "app_id": self.app_id})
        except Exception:
            pass
