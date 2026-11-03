"""从直播间链接读出网页房间号和真正的 room_id。"""
from __future__ import annotations

import re
from dataclasses import dataclass

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_ROOM_ID = (
    re.compile(r'roomId\\":\\"(\d+)\\"'),
    re.compile(r'"roomId":"(\d+)"'),
    re.compile(r'"room_id":"(\d+)"'),
    re.compile(r"room_id=(\d+)"),
)


@dataclass
class Room:
    web_rid: str
    room_id: str
    ttwid: str
    user_unique_id: str


def web_rid(text: str) -> str:
    raw = (text or "").strip()
    found = re.search(r"live\.douyin\.com/(\d+)", raw)
    if found:
        return found.group(1)
    if re.fullmatch(r"\d{5,}", raw):
        return raw
    return ""


def room_id_from_html(html: str) -> str:
    for pattern in _ROOM_ID:
        found = pattern.search(html or "")
        if found:
            return found.group(1)
    return ""


def resolve(text: str, client) -> Room:
    """client 是 httpx.Client。短链会跟着跳转。"""
    raw = (text or "").strip()
    if not raw:
        raise RuntimeError("先填直播间链接或房间号")
    rid = web_rid(raw)
    ttwid = ""
    html = ""
    if not rid and raw.startswith("http"):
        resp = client.get(raw, headers={"User-Agent": _UA}, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        rid = web_rid(str(resp.url))
        ttwid = resp.cookies.get("ttwid") or ""
        html = resp.text
        if not rid:
            rid = room_id_from_html(html)
    if not rid:
        raise RuntimeError("认不出直播间。要 live.douyin.com 的链接，或一串房间号")
    page = client.get(
        f"https://live.douyin.com/{rid}",
        headers={"User-Agent": _UA, "Cookie": f"ttwid={ttwid}" if ttwid else ""},
        follow_redirects=True,
        timeout=12,
    )
    page.raise_for_status()
    ttwid = page.cookies.get("ttwid") or ttwid
    room_id = room_id_from_html(page.text) or room_id_from_html(html)
    if not ttwid:
        home = client.get("https://live.douyin.com/", headers={"User-Agent": _UA}, timeout=12)
        ttwid = home.cookies.get("ttwid") or ""
    if not room_id:
        raise RuntimeError("直播间页面里没有房间号。确认这间正在播，并且链接能在浏览器里打开")
    did = ttwid[-19:] if len(ttwid) >= 19 else f"{int(rid):019d}"[-19:]
    if not did.isdigit():
        did = f"{int(rid):019d}"[-19:]
    return Room(web_rid=rid, room_id=room_id, ttwid=ttwid, user_unique_id=did)
