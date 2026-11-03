"""把这一眼的格子收成小可爱能用的短事实。不写她要说的那句。"""
from __future__ import annotations

from .catalog import slot_label
from .model import Brief, Phase, Sub

_EMPTY = "没看清"


def make_brief(sub: Sub, phase: Phase, slots: dict[str, str], surface: str = "") -> Brief:
    values = {slot: _value(slots, slot) for slot in phase.slots}
    if sub.kind in {"movie", "music", "video"}:
        from .media import handoff, company

        values.update({"title": slots.get("标题", ""), "artist": slots.get("歌手", ""),
                       "playback": slots.get("播放状态", ""), "version": slots.get("版本", ""),
                       "episode": slots.get("集数", ""), "switched": slots.get("内容切换", ""),
                       "seek": slots.get("跳转", ""),
                       "visual": slots.get("画面", ""), "transition": slots.get("经过", ""),
                       "subtitle": slots.get("这一句") or slots.get("原文") or "",
                       "audio": slots.get("听到", ""),
                       "media_id": slots.get("媒体标识", ""),
                       "line": slots.get("这一句") or slots.get("原文") or slots.get("听到") or "",
                       "caption": slots.get("这一句") or slots.get("原文") or slots.get("听到") or "",
                       "line_source": "screen" if slots.get("这一句") or slots.get("原文") else "audio" if slots.get("听到") else "window"})
        return Brief(active=True, kind=sub.kind, kind_label=_kind_label(sub.kind), sub=sub.id,
                     sub_label=sub.label, phase=phase.id, phase_label=phase.label, scene=sub.scene,
                     surface=surface, slots=values, still=True, handoff=handoff(sub, phase, slots) +
                     ("\n端：网页" if surface == "web" else "\n端：客户端" if surface == "client" else ""),
                     speak="只用当前确认的内容。没读到不等于不存在，不补写人物、歌手、歌词和情节。",
                     company=phase.company + company(sub.kind, slots) + "电影电视剧不提前透露后续。不从歌词推断用户的心情或经历。换集、换条、换歌和拖动进度后不拼接前后因果。" +
                     ("当前是电视剧集，不当作一部独立电影。" if slots.get("内容类型") == "电视剧" else ""))
    if sub.id == "league":
        sentence = _league_moment(phase, values, slots)
    else:
        sentence = _with_seen(_say(phase.say, sub.label, values), _seen(slots))
    where = _surface_label(surface)
    lines = [
        f"界面：{sub.label}",
        f"类型：{sub.scene}",
        f"标题：{sub.label}",
    ]
    if where:
        lines.append(f"端：{where}")
    lines.extend([
        f"原文：{sentence}",
        f"变化：{phase.label}",
    ])
    kind = _kind_label(sub.kind)
    return Brief(
        active=True,
        kind=sub.kind,
        kind_label=kind,
        sub=sub.id,
        sub_label=sub.label,
        phase=phase.id,
        phase_label=phase.label,
        scene=sub.scene,
        surface=surface,
        slots=values,
        still=True,
        handoff="\n".join(lines),
        speak=phase.speak,
        company=phase.company + (
            f"已确认用户这局操控的英雄是{values['hero']}。这是你这把{values['hero']}，不是在旁观别人。"
            "用第二人称接他的操作，不要叫他盯着自己的英雄，不要编对面是谁。"
            if sub.id == "league" and values.get("hero") not in {None, "", _EMPTY} else ""
        ),
    )


def _say(template: str, label: str, values: dict[str, str]) -> str:
    text = template or "现在在{label}"
    filled = text.replace("{label}", label)
    for slot, value in values.items():
        filled = filled.replace("{" + slot + "}", value or _EMPTY)
    if "{" in filled:
        return f"现在在{label}"
    return filled


def _clean(value: str) -> str:
    raw = (value or "").strip()
    if raw in {"", _EMPTY, "空", "无", "没有", "未知", "没变"}:
        return ""
    return raw


def _league_moment(phase: Phase, values: dict[str, str], slots: dict[str, str]) -> str:
    """交给她的是这一眼的动作，英雄名字跟着走。同一句重复的前缀越短，她才接得上新的一下。"""
    hero = _clean(values.get("hero", ""))
    state = _clean(values.get("state", ""))
    result = _clean(values.get("result", ""))
    items = _clean(values.get("items", ""))
    lane = _clean(values.get("lane", ""))
    mode = _clean(values.get("mode", ""))
    seen = _seen(slots)
    if phase.id == "load":
        # Splash-art poses belong to many loading cards, not the player's action.
        seen = _clean(slots.get("原文", ""))
    if phase.id == "score":
        seen = ""
    if phase.id == "dead" and hero:
        core = f"{hero}倒了，在等复活"
    elif phase.id == "score":
        core = "这局结束了" + (f"，{hero}" if hero else "") + (f"，{result}" if result else "")
    elif phase.id == "select" and hero:
        core = f"选了{hero}"
    elif phase.id == "fight":
        core = f"{hero}这边打起来了" if hero else "打起来了"
    elif hero and phase.id in {"load", "lane", "shop", "leave"}:
        head = {
            "load": "正在进这局",
            "lane": "在这局里",
            "shop": "在看装备",
            "leave": "准备出门",
        }[phase.id]
        core = f"{hero}{head}"
    else:
        core = {
            "launch": "英雄联盟正在打开",
            "lobby": "在英雄联盟大厅",
            "party": "在组队",
            "queue": "在排队",
            "select": "在选英雄",
            "load": "正在进这局",
            "shop": "在看装备",
            "leave": "准备出门",
            "lane": "在这局里",
            "dead": "倒了，在等复活",
        }.get(phase.id, phase.label)
        if result and result not in core:
            core = f"{core}，{result}"
    bits: list[str] = []
    if seen:
        bits.append(seen)
    if core and core not in (seen or ""):
        bits.append(core)
    for extra in (state, items, lane if phase.id in {"lane", "leave", "select"} else "", mode if phase.id in {"lobby", "party"} else ""):
        if extra and extra not in "。".join(bits):
            bits.append(extra)
    recent = _clean(slots.get("刚才", ""))
    if recent and recent not in "。".join(bits):
        bits.append(f"刚才：{recent[:100]}")
    return "。".join(bits) if bits else core


def _seen(slots: dict[str, str]) -> str:
    """画面上照抄下来的那句。空的是否不算看见。"""
    bits: list[str] = []
    for key in ("画面", "原文"):
        raw = (slots.get(key) or "").strip()
        if not raw or raw in {"是", "否", "没变", "空", "无", "没有", "没看清", "未知"}:
            continue
        if raw not in bits:
            bits.append(raw)
    return "，".join(bits)[:80]


def _drop_empty(sentence: str) -> str:
    """空着的格子不交给她，免得她对着「没看清」编。"""
    parts = [part.strip() for part in sentence.split("。")]
    kept = [part for part in parts if part and "没看清" not in part]
    return "。".join(kept)


def _with_seen(sentence: str, seen: str) -> str:
    sentence = _drop_empty(sentence)
    if not seen:
        return sentence
    if not sentence:
        return f"现在看见：{seen}"
    if seen in sentence:
        return sentence
    return f"{sentence}。现在看见：{seen}"


def _value(slots: dict[str, str], slot: str) -> str:
    raw = (slots.get(slot_label(slot)) or slots.get(slot) or "").strip()
    if raw in {"", "空", "无", "没有", "没看清", "未知"}:
        return _EMPTY
    return raw


def _surface_label(surface: str) -> str:
    if surface == "web":
        return "网页"
    if surface == "client":
        return "客户端"
    return ""


def _kind_label(kind_id: str) -> str:
    from .catalog import kind_of

    kind = kind_of(kind_id)
    return kind.label if kind else kind_id
