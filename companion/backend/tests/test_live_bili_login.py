"""B 站扫码登录自动化：虚构扫码响应，不保存真实账号信息。"""
from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.modules.live.bili.login import create_qrcode, poll_qrcode


def test_qr_login_auto_detects_account_and_room(monkeypatch):
    real_client = httpx.Client
    scan = {"state": 86101}
    cross_domain = "https://passport.biligame.com/crossDomain?" + urlencode({
        "SESSDATA": "fake-session", "DedeUserID": "42", "bili_jct": "fake-csrf",
    })

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/x/passport-login/web/qrcode/generate":
            return httpx.Response(200, json={"code": 0, "data": {
                "url": "https://passport.bilibili.com/login/scan?key=fake", "qrcode_key": "fake-key",
            }})
        if path == "/x/passport-login/web/qrcode/poll":
            assert request.url.params["qrcode_key"] == "fake-key"
            return httpx.Response(200, json={"code": 0, "data": {
                "code": scan["state"], "url": cross_domain if scan["state"] == 0 else "",
            }})
        if path == "/x/web-interface/nav":
            assert "fake-session" in request.headers.get("cookie", "")
            return httpx.Response(200, json={"code": 0, "data": {"mid": 42, "uname": "主播甲"}})
        if path == "/room/v1/Room/getRoomInfoOld":
            assert request.url.params["mid"] == "42"
            return httpx.Response(200, json={"code": 0, "data": {
                "roomStatus": 1, "roomid": 12345, "live_status": 1,
            }})
        raise AssertionError(path)

    transport = httpx.MockTransport(handler)

    def client_factory(*args, **kwargs):
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    created = create_qrcode()
    assert created["qrcode_key"] == "fake-key"
    assert created["image"].startswith("data:image/svg+xml;base64,")
    assert poll_qrcode("fake-key")["state"] == "waiting"
    scan["state"] = 86090
    assert poll_qrcode("fake-key")["state"] == "scanned"
    scan["state"] = 0
    done = poll_qrcode("fake-key")
    assert done["state"] == "done"
    assert done["room_id"] == "12345" and done["anchor"] == "主播甲"
    assert "SESSDATA=fake-session" in done["cookie"]
    assert "DedeUserID=42" in done["cookie"]
