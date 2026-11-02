"""一眼怎么来。窗口文字和听到的优先，眼睛只补画面里真正新发生的动作。"""
from __future__ import annotations

import time

from .desktop import Desk, Motion, find_media_hwnd, read_foreground, read_hwnd, window_box
from .hearing import ear

_TEXT = {"code", "slides", "document"}
_MEDIA = {"movie", "video", "game", "unknown"}
_EYE_FLOOR = 4.0
motion = Motion()
_last_eyes = 0.0
_last_text = ""
_pinned = 0


def reset() -> None:
    global _last_eyes, _last_text, _pinned
    _last_eyes = 0.0
    _last_text = ""
    _pinned = 0
    motion.reset()


def pick_line(eyes_text: str, previous: str = "") -> str:
    """这一眼里最新的一句能接的话。摆姿势、聊天窗和已经交过的句子都不算。"""
    from .situation import _caption, _line

    fresh = [
        line for line in _film_lines(eyes_text)
        if line not in {"没变", "画面没变"} and not _caption(line) and _line(line)
    ]
    if not fresh:
        return ""
    for line in reversed(fresh):
        if line not in (previous or ""):
            return line
    return ""


def should_call_eyes(
    kind: str,
    *,
    body: bool,
    named: bool,
    heard: bool,
    motion: str,
    force: bool,
    find: bool,
) -> bool:
    """找东西必须看图。代码和稿子已经有字就别看。歌有标题或歌词也不看。

    电影、视频、游戏：画面动了要看；画面很静，到了最大间隔也要看。
    编辑器读不到正文时，只在换窗口或到了间隔时看，不跟着每一次击键看。
    """
    if find:
        return True
    if kind in _TEXT and body:
        return False
    if kind == "browser" and (body or named):
        return False
    if kind == "music" and (body or heard):
        return False
    if kind == "music" and named and not force:
        return False
    if kind in _TEXT:
        return force or motion == "switched"
    if motion in {"switched", "moved"}:
        return True
    if force and kind in _MEDIA | {"music"}:
        return True
    return False


def _film_lines(text: str) -> list[str]:
    """「第1张：……」这种按时间排开的句子。不是这种格式就当没有。"""
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line.startswith("第") or "张" not in line[:4]:
            continue
        rest = line.split("：", 1)[1] if "：" in line else line.split(":", 1)[-1]
        rest = rest.strip()
        if rest and rest != line:
            lines.append(rest)
    return lines


def render(
    desk: Desk,
    heard: str,
    eyes_text: str = "",
    echo: list[str] | None = None,
) -> tuple[str, str]:
    """拼成眼睛原来那种分行事实。按张认出的字幕优先，没有字幕时才用听到的一句。"""
    from .situation import parse_observation, situation

    heard_line = "" if _echoes(heard, echo or []) else (heard or "").strip()
    eyes = parse_observation(eyes_text) if (eyes_text or "").strip() else None
    app = desk.app or (eyes.app if eyes else "")
    window = desk.window or (eyes.window if eyes else "")
    kind = desk.kind if desk.kind != "unknown" else (eyes.content_type if eyes else "unknown")
    if kind == "browser":
        kind = "unknown"
    title = desk.title or (eyes.title if eyes else "")
    chosen = pick_line(eyes_text, situation.progress)
    film = [chosen] if chosen else []
    if film:
        # 这一眼已经按张认出了字幕。杂音不能把字幕盖掉。
        texts = film
        channel = "screen"
    elif heard_line:
        texts = [heard_line]
        channel = "audio"
    elif desk.texts:
        texts = list(desk.texts)
        channel = "window"
    else:
        texts = list(eyes.visible_text) if eyes else []
        if texts or (eyes and eyes.visible_events):
            channel = "screen"
        elif desk.named and desk.kind in _TEXT | {"browser", "music"}:
            channel = "window"
        else:
            channel = "screen" if title else ""
    events = [] if film else (list(eyes.visible_events) if eyes else [])
    change = ""
    if film:
        change = film[-1]
    elif _film_lines(eyes_text):
        change = "没变"
    elif eyes and eyes.change:
        change = eyes.change
    elif heard_line:
        change = "听到这句"
    elif desk.texts:
        change = "窗口里的文字"
    elif title and channel == "window":
        change = "窗口是这个"
    if not (title or texts or events or change):
        return "", ""
    lines = []
    if app:
        lines.append(f"界面：{app}")
    if window:
        lines.append(f"窗口：{window}")
    if kind and kind != "unknown":
        lines.append(f"类型：{kind}")
    if title:
        lines.append(f"标题：{title}")
    for event in events[:2]:
        lines.append(f"画面：{event}")
    for text in texts[:2]:
        lines.append(f"原文：{text}")
    if change:
        lines.append(f"变化：{change}")
    return "\n".join(lines), channel


def collect(
    *,
    force: bool,
    before: str = "",
    echo: list[str] | None = None,
    find: bool = False,
    ask: str = "",
    along: bool = False,
    timeout: float = 30,
) -> dict:
    """陪看和口头看屏幕共用这一眼。返回的字典跟眼睛进程一样，多一个 channel。"""
    global _last_eyes, _last_text, _pinned
    desk = _stick(read_foreground())
    ear.bind(f"{desk.hwnd}:{desk.process}:{desk.title}")
    heard = _heard(desk, find)
    seen = motion.see(desk.hwnd) if desk.hwnd else "none"
    call = should_call_eyes(
        desk.kind,
        body=desk.body,
        named=desk.named,
        heard=bool(heard),
        motion=seen,
        force=force,
        find=find,
    )
    if call and not find and not force and seen != "switched" and time.time() - _last_eyes < _EYE_FLOOR:
        call = False
    from ..sight.service import commit as sight_commit
    from ..sight.service import prepare as sight_prepare

    order = sight_prepare(desk.process, desk.title, desk.window)
    found: dict = {"ok": True, "skipped": True, "text": "", "used_eyes": False}
    observed_at = time.time()
    if call:
        found = _look(desk, ask=ask, along=along, before=before, timeout=timeout, order=order)
        from .trace import mark

        mark(str(found.get("trace_id") or ""), source_process=desk.process,
             source_window=desk.window, source_title=desk.title)
        found["used_eyes"] = True
        _last_eyes = time.time()
        # The eye process reports capture time; never replace it with inference completion.
        found.setdefault("observed_at", observed_at)
        observed_at = float(found.get("observed_at") or observed_at)
        if not found.get("ok"):
            return found
    eyes_text = str(found.get("text") or "") if found.get("ok") and not found.get("skipped") else ""
    if found.get("ocr_text"):
        eyes_text += "\n" + str(found["ocr_text"])
    if found.get("terminal_only"):
        from ..sight.league import result

        outcome = result(eyes_text)
        if not outcome:
            return {**found, "ok": True, "skipped": True, "text": "", "stale": True}
        eyes_text = "结果：" + outcome
    if order.sub == "league" and call:
        from ..sight.league import observation_timing
        timing = observation_timing(order.phase, eyes_text, time.time() - observed_at)
        from .trace import mark
        mark(str(found.get("trace_id") or ""), **timing)
        if float(timing["capture_age"]) > float(timing["freshness_limit"]):
            return {**found, "ok": True, "skipped": True, "text": "", "stale": True,
                    "message": "识别结果已过期，等待新画面"}
    found["script"] = eyes_text
    if (order.kind or desk.kind) in {"movie", "video", "music"}:
        from ..sight.media import inputs
        from .media_session import latest

        metadata = latest(desk)
        from ..sight.service import current
        from ..sight.media import title as media_title

        old_title = current().slots.get("title")
        next_title = media_title(str(metadata.get("title") or desk.title), desk.app)
        if old_title and next_title and old_title != next_title:
            ear.clear()
            heard = ""
        eyes_text = inputs(desk, eyes_text, heard, metadata=metadata, echo=_echoes(heard, echo or []))
        found["media_inputs"] = eyes_text
    if order.sub == "league" and desk.process.lower() == "league of legends.exe" and call:
        from ..sight.league_client import latest

        state = latest()
        if state:
            eyes_text += f"\n英雄：{state['hero']}\n身份来源：liveclient\n对局时钟：{state['game_time']}"
            if state["dead"]:
                eyes_text += f"\n原文：返回于 {int(state['respawn'])}\n阶段：阵亡"
    brief = sight_commit(desk.process, desk.title, desk.window, eyes_text)
    if brief.active and brief.handoff:
        if brief.handoff == _last_text and not find:
            return {
                "ok": True,
                "skipped": True,
                "text": "",
                "channel": "sight",
                "source": "screen",
                "used_eyes": bool(call),
                "sight": brief.public(),
                "trace_id": str(found.get("trace_id") or ""),
            }
        _last_text = brief.handoff
        found = {
            **found,
            "ok": True,
            "skipped": False,
            "text": brief.handoff,
            "channel": "sight",
            "source": "screen",
            "sight": brief.public(),
        }
        if brief.kind in {"movie", "video", "music"}:
            found["channel"] = brief.slots.get("line_source") or "screen"
            if brief.slots.get("switched") or brief.slots.get("seek"):
                found["continuity_gap"] = "媒体内容切换或进度跳转，不保证前后连续"
        _trace(found, called=call)
        return found
    text, channel = render(desk, heard, eyes_text, echo)
    if text and text == _last_text and not find:
        return {
            "ok": True,
            "skipped": True,
            "text": "",
            "channel": channel,
            "source": "screen",
            "used_eyes": bool(call),
            "trace_id": str(found.get("trace_id") or ""),
        }
    if text:
        _last_text = text
        found = {**found, "ok": True, "skipped": False, "text": text, "channel": channel, "source": "screen"}
        _trace(found, called=call)
        return found
    if call and not found.get("ok"):
        found["channel"] = ""
        return found
    return {
        "ok": True,
        "skipped": True,
        "text": "",
        "channel": "",
        "source": "screen",
        "used_eyes": bool(call),
        "trace_id": str(found.get("trace_id") or ""),
        "message": str(found.get("message") or ""),
    }


def _lab_page(desk: Desk) -> bool:
    blob = f"{desk.window} {desk.title}"
    return "陪看记录" in blob or "小可爱" in blob


def _game_window(desk: Desk) -> bool:
    if not desk.hwnd or not desk.process:
        return False
    try:
        from ..sight.match import match

        hit = match(desk.process, desk.title, desk.window)
    except Exception:
        return False
    return hit is not None and hit.kind == "game"


def _keep_watch(desk: Desk) -> bool:
    """这一窗是正在看的片子或游戏。陪看记录页本身不算。"""
    if not desk.ok or not desk.hwnd or _lab_page(desk):
        return False
    if desk.kind in {"video", "movie", "music"}:
        return True
    return _game_window(desk)


def _stick(desk: Desk) -> Desk:
    """一起看时前台若切到陪看页或编辑器，眼睛仍留在正在看的那一窗。"""
    global _pinned
    try:
        from .along import snapshot

        watching = bool(snapshot().get("on"))
    except Exception:
        watching = False
    if not watching:
        return desk
    if _keep_watch(desk):
        _pinned = desk.hwnd
        return desk
    stuck = read_hwnd(_pinned) if _pinned else Desk()
    if _keep_watch(stuck):
        return stuck
    hwnd = find_media_hwnd()
    stuck = read_hwnd(hwnd) if hwnd else Desk()
    if _keep_watch(stuck):
        _pinned = stuck.hwnd
        return stuck
    return desk


def _heard(desk: Desk, find: bool) -> str:
    if find or desk.kind not in {"music", "movie", "video", "game"}:
        return ""
    got = ear.latest()
    if got:
        return got
    try:
        from .along import snapshot

        running = bool(snapshot().get("on"))
    except Exception:
        running = False
    if running:
        return ""
    return ear.once(2.0)


def _look(desk: Desk, *, ask: str, along: bool, before: str, timeout: float, order=None) -> dict:
    from .service import eyes_glance
    from .vision import uses_local

    hint = ""
    if desk.window:
        hint = (
            f"前台是{desk.app or '这个程序'}，窗口「{desk.window}」。"
            "只写这个窗口里新发生的动作或原文。不要写其他窗口，不要写旁边的动漫角色。\n"
        )
    context = hint + (before or "")
    box = window_box(desk.hwnd) if desk.hwnd else None
    bound = order is not None and getattr(order, "active", False)
    prompt = order.prompt if bound else ""
    if bound and order.sub == "league" and not uses_local():
        from ..sight.league import detailed_prompt

        prompt = detailed_prompt()
    return eyes_glance(
        prompt or ask,
        along,
        timeout=timeout,
        before=context,
        gate=False,
        detail=(order.detail if bound else False) or desk.kind in {"code", "slides"},
        crop=box,
        prompt=prompt,
        frames=order.frames if bound else 0,
        window_hwnd=desk.hwnd,
    )


def _trace(found: dict, *, called: bool) -> None:
    from .trace import mark, note_look

    if called and found.get("trace_id"):
        script = str(found.get("script") or "")
        mark(str(found.get("trace_id")), result=script or str(found.get("text") or ""), media_inputs=str(found.get("media_inputs") or ""))
        return
    if called:
        return
    found["trace_id"] = note_look(
        found,
        {"prompt": "前台窗口和系统声。这一眼没有叫眼睛。"},
        ask="",
        gate=False,
        detail=False,
    )


def _echoes(heard: str, recent: list[str]) -> bool:
    left = _grams(heard)
    if not left:
        return False
    for line in recent:
        right = _grams(line)
        if not right:
            continue
        if len(left & right) / min(len(left), len(right)) >= 0.62:
            return True
    return False


def _grams(text: str) -> set[str]:
    import re

    kept = re.sub(r"[^\w\u4e00-\u9fff]+", "", text or "")
    if len(kept) < 2:
        return set()
    return {kept[i:i + 2] for i in range(len(kept) - 1)}
