"""用户主动扫码登录；成功后自动取本人房间，不读取浏览器或直播姬凭据。"""
from __future__ import annotations

import base64
import io
from urllib.parse import parse_qs, urlparse

import httpx

from .web import USER_AGENT, cookie_items

PASSPORT = "https://passport.bilibili.com/x/passport-login/web/qrcode"
WEB_API = "https://api.bilibili.com"
LIVE_API = "https://api.live.bilibili.com"
_COOKIE_KEYS = ("SESSDATA", "DedeUserID", "DedeUserID__ckMd5", "bili_jct")
_HEADERS = {"User-Agent": USER_AGENT, "Referer": "https://passport.bilibili.com/login"}


def _data(resp: httpx.Response) -> dict:
    if resp.status_code != 200:
        raise RuntimeError(f"登录接口返回 {resp.status_code}")
    payload = resp.json()
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(str(payload.get("message") or "登录接口拒绝")[:180])
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def create_qrcode() -> dict:
    import qrcode
    import qrcode.image.svg

    with httpx.Client(headers=_HEADERS, timeout=15, trust_env=False) as client:
        data = _data(client.get(PASSPORT + "/generate"))
    url = str(data.get("url") or "")
    key = str(data.get("qrcode_key") or "")
    if not url or not key:
        raise RuntimeError("没有取得登录二维码")
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    out = io.BytesIO()
    image.save(out)
    encoded = base64.b64encode(out.getvalue()).decode("ascii")
    return {"qrcode_key": key, "image": f"data:image/svg+xml;base64,{encoded}", "expires_in": 180}


def _login_cookies(resp: httpx.Response, data: dict) -> str:
    found = {key: resp.cookies.get(key) for key in _COOKIE_KEYS if resp.cookies.get(key)}
    # 部分响应通过 crossDomain URL 返回同一组凭据。
    query = parse_qs(urlparse(str(data.get("url") or "")).query)
    for key in _COOKIE_KEYS:
        if key not in found and query.get(key):
            found[key] = query[key][0]
    if not found.get("SESSDATA") or not found.get("DedeUserID"):
        raise RuntimeError("登录成功但没有取得完整 Cookie，请重试")
    return "; ".join(f"{key}={value}" for key, value in found.items())


def account_room(cookie: str) -> dict:
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"}
    with httpx.Client(headers=headers, timeout=15, follow_redirects=True, trust_env=False) as client:
        for key, value in cookie_items(cookie):
            client.cookies.set(key, value, domain=".bilibili.com")
        nav = _data(client.get(WEB_API + "/x/web-interface/nav"))
        mid = int(nav.get("mid") or 0)
        if not mid:
            raise RuntimeError("登录态无效，请重新扫码")
        room = _data(client.get(LIVE_API + "/room/v1/Room/getRoomInfoOld", params={"mid": mid}))
    return {
        "uid": str(mid),
        "anchor": str(nav.get("uname") or ""),
        "room_id": str(room.get("roomid") or "") if int(room.get("roomStatus") or 0) else "",
        "live_status": int(room.get("live_status") or 0),
    }


def poll_qrcode(key: str) -> dict:
    with httpx.Client(headers=_HEADERS, timeout=15, trust_env=False) as client:
        resp = client.get(PASSPORT + "/poll", params={"qrcode_key": key})
        data = _data(resp)
    state = int(data.get("code") if data.get("code") is not None else 86101)
    if state == 86101:
        return {"state": "waiting"}
    if state == 86090:
        return {"state": "scanned"}
    if state == 86038:
        return {"state": "expired", "error": "二维码已过期，请重新生成"}
    if state != 0:
        raise RuntimeError(str(data.get("message") or f"扫码登录失败（{state}）")[:180])
    cookie = _login_cookies(resp, data)
    account = account_room(cookie)
    return {"state": "done", "cookie": cookie, **account}
