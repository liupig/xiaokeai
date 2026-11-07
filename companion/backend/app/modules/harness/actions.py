"""Host boundaries for agent-selected actions; intent is chosen by dsh."""
from __future__ import annotations

import re
import threading
import time

_WEB_FACT = re.compile(r"金价|黄金价格|股价|股票价格|汇率|油价|天气|新闻|比分|最新版本|补丁更新|攻略|赛程|航班")
_SCREEN = re.compile(r"屏幕|画面|桌面|窗口|截图|这张图|图里|图上|报错|这一局|这局|当前网页|这个网页|网页上|页面上|这一页|这页")
_BARE = re.compile(r"麻烦|帮我|帮忙|请|您|你|能不能|能否|可以|好不好|行不行|看一看|看一下|看一眼|看看|瞅一瞅|瞅瞅|瞅一眼|看|瞅|一下|一眼|吧|呗|吗|嘛|呀|啊|呢|哦|[\s。！？!?，,～~]")


def visual_request_policy(user_text: str, prior=None, *, screen_context: bool = False) -> str:
    """A model action cannot turn a public-fact query into a screen capture.

    This is a negative execution guard, not the intent router. Explicit screen
    references take precedence: reading a gold price visible in a screenshot is
    different from checking today's gold price online.
    """
    raw = user_text or ""
    compact = re.sub(r"\s+", "", raw)
    if re.fullmatch(r"(?:你|我)?(?:现在|正在)?(?:在干嘛|在干吗|在干什么|在做什么)[呢吗啊呀？?。！!]*", compact):
        return "chat"
    if _SCREEN.search(raw):
        return "allow"
    if _WEB_FACT.search(raw):
        return "lookup"
    recent = [str(item.get("content") or "") for item in prior or [] if item.get("role") == "user"]
    if len(raw.strip()) <= 16:
        if recent and _WEB_FACT.search(recent[-1]) and not _SCREEN.search(recent[-1]):
            return "lookup"
    bare = _BARE.sub("", raw) in {"", "这个", "那个", "这", "那"} and any(word in raw for word in ("看", "瞅"))
    if bare and not screen_context and not any(_SCREEN.search(str(item.get("content") or "")) for item in (prior or [])[-4:]):
        return "clarify"
    return "allow"


def visual_request_allowed(user_text: str, prior=None) -> bool:
    return visual_request_policy(user_text, prior) == "allow"


def play_note(query: str, locale: str, *, host=None) -> str:
    from ..play.service import open_game, _hint
    from ..sight.service import hold_name

    name = (query or "").strip()
    if not name or len(name) > 80:
        return "【开游戏】没有明确的游戏名，请询问对方要开哪一个。"
    region = "cn" if (locale or "").lower().startswith("zh") else "intl"
    result = open_game(name, region=region, host=host)
    if result.get("state") not in {"failed", "not_found", "no_launcher"}:
        hold_name(name)
    return _hint(result) or f"【开游戏】没有找到{name}，不能声称已经打开。"


def prepare_visual(ask: str, character_id: int, cancel: threading.Event, *, timeout: float = 90) -> str:
    from ..glance import along, eyes_host
    from ..glance.service import parse_glance

    value = (ask or "").strip()
    if value == "关闭":
        along.stop()
        eyes_host.shutdown()
        return "closed"
    capability = eyes_host.capability()
    if not capability["available"]:
        return capability["message"]
    if cancel.is_set():
        return "这一轮已打断"
    state = eyes_host.ensure()
    if state == "missing":
        return "眼睛环境还没装好"
    if state == "failed":
        return eyes_host.eyes_status().get("message") or "视觉模型启动失败"
    deadline = time.monotonic() + timeout
    while state == "starting":
        if cancel.wait(0.25):
            return "这一轮已打断"
        if time.monotonic() >= deadline:
            return "视觉仍在加载，暂时还没看见屏幕"
        status = eyes_host.eyes_status()
        state = status["eyes"]
        if state == "down":
            return status.get("message") or "视觉启动失败，暂时看不到屏幕"
    if cancel.is_set():
        return "这一轮已打断"
    eyes_host.enable_glance()
    _, continuous = parse_glance(value)
    if continuous or value == "开启":
        along.start(character_id, request=value)
    return ""
