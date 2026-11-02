"""前台窗口对上哪一个内置体验。网页要落在浏览器里，客户端看进程。"""
from __future__ import annotations

import re

from .catalog import kinds
from .model import Hit

_RANK = {"game": 50, "work": 40, "movie": 30, "music": 20, "video": 10}
_BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}


def norm(text: str) -> str:
    raw = (text or "").lower().strip()
    return re.sub(r"[\s_\-·:：'\"“”]+", "", raw)


def match(process: str, title: str, window: str) -> Hit | None:
    proc = (process or "").lower().strip()
    blob = f"{title or ''} {window or ''}".lower()
    best: Hit | None = None
    for kind in kinds():
        for sub in kind.subs:
            score, hint, surface = _score(sub.match, sub.processes, sub.titles, sub.process_phase, proc, blob)
            if score <= 0:
                continue
            score += _RANK.get(kind.id, 0) + _page_penalty(blob, sub.id)
            if score <= 0:
                continue
            if best is None or score > best.score:
                best = Hit(kind=kind.id, sub=sub.id, score=score, phase_hint=hint, surface=surface)
    return best


def _score(mode: str, processes: tuple[str, ...], titles: tuple[str, ...], hints: dict[str, str], process: str, blob: str) -> tuple[int, str, str]:
    hint = hints.get(process, "") if process else ""
    if process and process in processes:
        return 100, hint, "client"
    title_hit = _title(blob, titles)
    if title_hit <= 0 or mode == "process":
        return 0, "", ""
    browser = process in _BROWSERS
    if mode in {"web", "split"} and not browser:
        return 0, "", ""
    if mode == "web":
        return 60 + title_hit, "", "web"
    if mode == "title":
        return 40 + title_hit, "", "web" if browser else "client"
    if mode in {"either", "split"}:
        return 50 + title_hit, "", "web" if browser else "client"
    return 0, "", ""


# 标题里先出现这些，就说明人还在这个网站上，别被片子或歌名里的别的牌子抢走。
_PAGES = (
    ("music.youtube.com", "youtubemusic"),
    ("youtube music", "youtubemusic"),
    ("youtu.be", "youtube"),
    ("youtube", "youtube"),
    ("bilibili", "bilibili"),
    ("nicovideo", "niconico"),
    ("twitch.tv", "twitch"),
    ("chzzk.naver", "chzzk"),
    ("sooplive", "soop"),
    ("afreecatv", "soop"),
    ("abema.tv", "abema"),
    ("instagram.com", "instagram"),
    ("tiktok.com", "tiktok"),
    ("douyin.com", "douyin"),
)


def _page_penalty(blob: str, sub_id: str) -> int:
    owner = ""
    for key, sid in _PAGES:
        if key in blob:
            owner = sid
            break
    if owner and owner != sub_id:
        return -120
    return 0


def _title(blob: str, titles: tuple[str, ...]) -> int:
    best = 0
    for item in titles:
        key = item.lower()
        if key and key in blob:
            best = max(best, len(key))
    return best
