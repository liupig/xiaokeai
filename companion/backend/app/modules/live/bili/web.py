"""直播姬/OBS 通用：连接网页直播间信息流，只收互动，不接管推流。"""
from __future__ import annotations

import json
import re
import threading
import time
from http.cookies import SimpleCookie
from typing import Callable

import httpx

from ..events import LiveEvent
from .packet import OP_AUTH, OP_AUTH_REPLY, OP_HEARTBEAT, OP_NOTIFY, pack_packet, unpack_packets
from .parse import events_from_json
from .wbi import sign_params

API = "https://api.live.bilibili.com"
WEB_API = "https://api.bilibili.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
_OnEvent = Callable[[LiveEvent], None]
_OnStatus = Callable[[dict], None]


def normalize_room(value: str) -> str:
    text = str(value or "").strip()
    if text.isdigit():
        return text
    match = re.search(r"live\.bilibili\.com/(?:[a-z]+/)?(\d+)", text, re.I)
    return match.group(1) if match else ""


def cookie_items(raw: str) -> list[tuple[str, str]]:
    parsed = SimpleCookie()
    try:
        parsed.load(str(raw or "").strip())
    except Exception:
        return []
    return [(key, morsel.value) for key, morsel in parsed.items() if key and morsel.value]


class WebLiveSession:
    def __init__(self, room: str, cookie: str, on_event: _OnEvent, on_status: _OnStatus) -> None:
        self.room = normalize_room(room)
        self.cookie = str(cookie or "").strip()
        self._on_event = on_event
        self._on_status = on_status
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.reconnects = 0
        self.state = "idle"
        self.error = ""
        self.anchor = ""
        self.room_id = ""

    def snapshot(self) -> dict:
        return {
            "state": self.state, "error": self.error, "anchor": self.anchor,
            "room_id": self.room_id, "reconnects": self.reconnects, "mode": "web",
        }

    def start(self) -> None:
        self.stop()
        self._stop = threading.Event()
        self.error = ""
        self.state = "connecting"
        self._emit()
        thread = threading.Thread(target=self._run, name="live-bili-web", daemon=True)
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=8)
        self._thread = None
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
                raise RuntimeError("直播间长连接断开")
            except Exception as exc:
                if self._stop.is_set():
                    break
                self.reconnects += 1
                self.error = str(exc)[:180]
                self.state = "down" if self.reconnects > 8 else "reconnecting"
                self._emit()
                if self.reconnects > 8 or self._stop.wait(delay):
                    break
                delay = min(delay * 2, 30)
        self.state = "idle" if self._stop.is_set() else self.state
        self._emit()

    @staticmethod
    def _json(resp: httpx.Response, *, allow: tuple[int, ...] = ()) -> dict:
        if resp.status_code != 200:
            raise RuntimeError(f"B 站接口返回 {resp.status_code}")
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("B 站接口没有返回 JSON") from exc
        code = int(payload.get("code") or 0)
        if code != 0 and code not in allow:
            message = str(payload.get("message") or payload.get("msg") or "B 站接口拒绝")
            raise RuntimeError(message[:180])
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def _prepare(self) -> dict:
        headers = {"User-Agent": USER_AGENT, "Referer": "https://live.bilibili.com/"}
        with httpx.Client(headers=headers, timeout=httpx.Timeout(15, connect=8),
                          follow_redirects=True, trust_env=False) as client:
            for key, value in cookie_items(self.cookie):
                client.cookies.set(key, value, domain=".bilibili.com")
            if not client.cookies.get("buvid3"):
                finger = self._json(client.get(WEB_API + "/x/frontend/finger/spi"))
                buvid = str(finger.get("b_3") or "")
                if not buvid:
                    raise RuntimeError("没有取得 buvid3，请填写含 buvid3 的 Cookie")
                client.cookies.set("buvid3", buvid, domain=".bilibili.com")

            room_data = self._json(client.get(API + "/room/v1/Room/room_init", params={"id": self.room}))
            room_id = int(room_data.get("room_id") or 0)
            if not room_id:
                raise RuntimeError("房间号不存在或无法读取")

            # 未登录也返回 wbi_img，但 code 是 -101。
            nav = self._json(client.get(WEB_API + "/x/web-interface/nav"), allow=(-101,))
            wbi = nav.get("wbi_img") if isinstance(nav.get("wbi_img"), dict) else {}
            img_key = str(wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".", 1)[0]
            sub_key = str(wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".", 1)[0]
            if len(img_key) != 32 or len(sub_key) != 32:
                raise RuntimeError("没有取得 WBI 签名参数")
            params = sign_params({"id": room_id, "type": 0, "web_location": "444.8"}, img_key, sub_key)
            info = self._json(client.get(API + "/xlive/web-room/v1/index/getDanmuInfo", params=params))
            hosts = info.get("host_list") if isinstance(info.get("host_list"), list) else []
            host = hosts[0] if hosts and isinstance(hosts[0], dict) else {}
            name = str(host.get("host") or "")
            port = int(host.get("wss_port") or 443)
            token = str(info.get("token") or "")
            if not token or not (name == "bilibili.com" or name.endswith(".bilibili.com")):
                raise RuntimeError("B 站没有给全弹幕长连接信息")
            uid = int(client.cookies.get("DedeUserID") or 0)
            buvid = str(client.cookies.get("buvid3") or "")
            return {
                "room_id": room_id,
                "wss": f"wss://{name}:{port}/sub",
                "auth": {"uid": uid, "roomid": room_id, "protover": 3, "buvid": buvid,
                         "platform": "web", "type": 2, "key": token},
                "cookie": "; ".join(
                    f"{key}={value}"
                    for key, value in (dict(cookie_items(self.cookie)) | {"buvid3": buvid}).items()
                ),
            }

    def _session_once(self) -> None:
        import websocket

        info = self._prepare()
        self.room_id = str(info["room_id"])
        self.state = "live"
        self.error = ""
        self._emit()
        ws = websocket.create_connection(
            info["wss"], timeout=15, origin="https://live.bilibili.com",
            header=[f"User-Agent: {USER_AGENT}", f"Cookie: {info['cookie']}"],
        )
        try:
            auth = json.dumps(info["auth"], separators=(",", ":")).encode("utf-8")
            ws.send(pack_packet(OP_AUTH, auth, proto=1), opcode=0x2)
            ws.settimeout(1.0)
            last_hb = time.time()
            buf = b""
            authenticated = False
            while not self._stop.is_set():
                now = time.time()
                if now - last_hb >= 30:
                    ws.send(pack_packet(OP_HEARTBEAT, b"", proto=1), opcode=0x2)
                    last_hb = now
                try:
                    chunk = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not chunk:
                    raise RuntimeError("直播间长连接断开")
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                buf += chunk
                packets, buf = unpack_packets(buf)
                for op, body in packets:
                    if op == OP_AUTH_REPLY:
                        reply = json.loads(body or b"{}")
                        if int(reply.get("code") or 0) != 0:
                            raise RuntimeError("直播间认证失败，请检查 Cookie")
                        authenticated = True
                    elif op == OP_NOTIFY:
                        for ev in events_from_json(body):
                            self._on_event(ev)
                if not authenticated and now - last_hb > 5:
                    raise RuntimeError("直播间认证超时")
        finally:
            try:
                ws.close()
            except Exception:
                pass
