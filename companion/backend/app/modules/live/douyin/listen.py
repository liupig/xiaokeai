"""连一间公开直播间，把弹幕收进 inbox。不代登录，不代开播。"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

import httpx

from . import browser, inbox
from .messages import events_from_body
from .room import _UA, resolve

_SIGN_KEYS = (
    "live_id", "aid", "version_code", "webcast_sdk_version",
    "room_id", "sub_room_id", "sub_channel_id", "did_rule",
    "user_unique_id", "device_platform", "device_type", "ac", "identity",
)
_FETCH = "https://live.douyin.com/webcast/im/fetch/"

class _Job:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None


_lock = threading.Lock()
_job: _Job | None = None
_state: dict[str, Any] = {
    "listening": False,
    "room": "",
    "web_rid": "",
    "room_id": "",
    "error": "",
}


def snapshot() -> dict[str, Any]:
    with _lock:
        out = dict(_state)
    out["seq"] = inbox.snapshot_seq()
    return out


def _set(**kwargs: Any) -> None:
    with _lock:
        changed = kwargs.get("error")
        prev = _state.get("error")
        _state.update(kwargs)
    if changed and changed != prev:
        print(f"[live] {changed}")


def stop() -> dict[str, Any]:
    global _job
    with _lock:
        job = _job
        _job = None
        _state["listening"] = False
    if job is not None:
        job.stop.set()
        thread = job.thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=8)
    return snapshot()


def start(room: str) -> dict[str, Any]:
    global _job
    stop()
    inbox.clear()
    job = _Job()
    _set(listening=True, room=(room or "").strip(), web_rid="", room_id="", error="")
    thread = threading.Thread(target=_run, name="live-douyin", args=((room or "").strip(), job), daemon=True)
    job.thread = thread
    with _lock:
        _job = job
    thread.start()
    return snapshot()


def _signature(params: dict) -> str:
    text = ",".join(f"{key}={params.get(key, '')}" for key in _SIGN_KEYS)
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _params(page, cursor: str, internal: str) -> dict[str, str]:
    now = str(int(time.time() * 1000))
    return {
        "app_name": "douyin_web",
        "version_code": "180800",
        "webcast_sdk_version": "1.0.14-beta.0",
        "update_version_code": "1.0.14-beta.0",
        "compress": "gzip",
        "device_platform": "web",
        "cookie_enabled": "true",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Mozilla",
        "browser_online": "true",
        "tz_name": "Asia/Shanghai",
        "cursor": cursor or f"t-{now}_r-1",
        "internal_ext": internal or (
            f"internal_src:dim|wss_push_room_id:{page.room_id}|wss_push_did:{page.user_unique_id}"
            f"|first_req_ms:{now}|fetch_time:{now}|seq:1|wss_info:0-{now}-0-0"
        ),
        "host": "https://live.douyin.com",
        "aid": "6383",
        "live_id": "1",
        "did_rule": "3",
        "endpoint": "live_pc",
        "support_wrds": "1",
        "user_unique_id": page.user_unique_id,
        "im_path": "/webcast/im/fetch/",
        "identity": "audience",
        "need_persist_msg_count": "15",
        "room_id": page.room_id,
        "heartbeatDuration": "0",
        "sub_room_id": "",
        "sub_channel_id": "",
        "device_type": "",
        "ac": "",
    }


def _headers(page) -> dict[str, str]:
    cookie = f"ttwid={page.ttwid}" if page.ttwid else ""
    return {
        "User-Agent": _UA,
        "Referer": f"https://live.douyin.com/{page.web_rid}",
        "Cookie": cookie,
    }


def fetch_once(client: httpx.Client, page, cursor: str, internal: str) -> tuple[list[dict], str, str]:
    params = _params(page, cursor, internal)
    params["signature"] = _signature(params)
    resp = client.get(_FETCH, params=params, headers=_headers(page), timeout=12)
    if resp.status_code >= 400:
        raise RuntimeError(f"弹幕接口返回 {resp.status_code}")
    if not resp.content:
        raise RuntimeError(
            "弹幕通道没有返回数据。网页这条要直播页里现算的签名，这一版对不上。"
            "小玩法的评论可以发到 /api/modules/live/douyin/callback"
        )
    events, next_cursor, next_internal = events_from_body(resp.content)
    return events, next_cursor or cursor, next_internal or internal


def _run(room: str, job: _Job) -> None:
    try:
        with httpx.Client(follow_redirects=True, timeout=12) as client:
            page = resolve(room, client)
        if job.stop.is_set():
            return
        _set(web_rid=page.web_rid, room_id=page.room_id, error="正在打开直播间")
        url = f"https://live.douyin.com/{page.web_rid}"

        def on_events(events: list[dict]) -> None:
            if inbox.add_many(events):
                _set(error="")
            if any(item.get("kind") == "control" for item in events):
                _set(error="这场直播结束了")
                job.stop.set()

        browser.watch(url, on_events, job.stop, on_ready=lambda: _set(error=""))
    except Exception as exc:
        if not job.stop.is_set():
            _set(error=str(exc)[:200])
    finally:
        with _lock:
            if _job is job:
                _state["listening"] = False
