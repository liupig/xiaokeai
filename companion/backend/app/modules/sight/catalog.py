"""内置体验和本机加上的子类。子类是配置，不是另一段识别代码。"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from ...paths import DATA_DIR
from .model import Kind, Phase, Sub

_SLOT = {
    "hero": "英雄",
    "items": "装备",
    "lane": "线路",
    "state": "局面",
    "result": "结果",
    "title": "名字",
    "artist": "歌手",
    "line": "原文",
    "caption": "这一条",
    "file": "文件",
    "error": "报错",
    "page": "这一页",
    "mode": "模式",
    "host": "主播",
    "map": "地图",
    "weapon": "武器",
    "side": "阵营",
    "place": "地点",
    "boss": "首领",
    "runes": "卢恩",
}
_lock = threading.Lock()
_kinds: tuple[Kind, ...] = ()


def slot_label(slot: str) -> str:
    return _SLOT.get(slot, slot)


def overlay_path() -> Path:
    home = (os.environ.get("SIGHT_HOME") or "").strip()
    if home:
        return Path(home) / "subs.json"
    return DATA_DIR / "sight" / "subs.json"


def reload() -> tuple[Kind, ...]:
    global _kinds
    with _lock:
        _kinds = _load()
        return _kinds


def kinds() -> tuple[Kind, ...]:
    if not _kinds:
        return reload()
    return _kinds


def kind_of(kind_id: str) -> Kind | None:
    for item in kinds():
        if item.id == kind_id:
            return item
    return None


def find_sub(kind_id: str, sub_id: str) -> Sub | None:
    kind = kind_of(kind_id)
    if kind is None:
        return None
    return kind.sub(sub_id)


def find_named(name: str) -> Sub | None:
    from .match import norm

    key = norm(name)
    if not key:
        return None
    for kind in kinds():
        for sub in kind.subs:
            if key == norm(sub.id) or key == norm(sub.label) or any(key == norm(item) for item in sub.names):
                return sub
    return None


def ahead_ids(sub: Sub, phase: Phase) -> set[str]:
    """这一眼允许确认的下一屏。没写的话，只允许顺着进度往前一步。"""
    chosen = phase.ahead or _default_ahead(sub, phase)
    return {item for item in chosen if item != phase.id and sub.phase(item) is not None}


def _default_ahead(sub: Sub, phase: Phase) -> tuple[str, ...]:
    for index, item in enumerate(sub.phases):
        if item.id == phase.id and index + 1 < len(sub.phases):
            return (sub.phases[index + 1].id,)
    return ()


def _hero_hint(sub: Sub, phase: Phase) -> str:
    """英雄联盟的加载卡和镜头正中才是他这局的英雄。别的游戏没有这块版式。"""
    if sub.id == "league" and phase.id in {"load", "shop", "leave", "lane", "fight", "dead", "score"}:
        return "英雄只写玩家自己的那一个。加载画面写正中间最大那张立绘下沿的名字，底下横排是别人，不要写。已经在局里就写画面正中的那个。认不准就空着。"
    if sub.id == "league":
        return "英雄只写他已经锁定的那个名字。还在挑、认不准，就空着。"
    return "英雄只写画面上认得准的名字，中间最大的那张卡优先。认不准就空着。"


def prompt_for(sub: Sub, phase: Phase, surface: str = "") -> str:
    """先让模型照抄看见的字，再用画面对阶段。不给一个只能选的词。"""
    del surface
    if sub.id == "league":
        from .league import prompt

        return prompt()
    if sub.kind in {"movie", "music", "video"}:
        from .media import prompt

        return prompt(sub.kind)
    nxt = [sub.phase(item) for item in phase.ahead or _default_ahead(sub, phase)]
    nxt = [item for item in nxt if item is not None]
    lines = [
        "先看画面上有什么。这几张按时间从早到晚，以最后一张为准。",
        "原文照抄画面上能读到的字，不要改写成阶段的名字。",
        "阶段只有和下面某一条对得上才写，对不上就空着。不要因为名单里有这个词就写它。",
        "这张如果是陪看记录，或不是这个窗口，阶段空着，仍在写否。",
        "画面：",
        "原文：",
    ]
    if nxt:
        lines.append("对得上才写阶段：")
        for item in nxt:
            lines.append(f"{item.label}：{item.mark}" if item.mark else item.label)
    else:
        lines.append(f"还是这一屏就写{phase.label}，不是就让阶段空着。")
    lines.append("阶段：")
    asked: list[str] = []
    for item in [phase, *nxt]:
        for slot in item.slots:
            label = slot_label(slot)
            if label not in asked:
                asked.append(label)
                lines.append(f"{label}：")
    if "英雄" in asked:
        lines.append(_hero_hint(sub, phase))
    if sub.id == "league" and phase.id in {"load", "shop", "leave", "lane", "fight", "dead", "score"}:
        lines.append("画面用一句说这个英雄此刻在干什么。屏幕上有返回于，就把秒数一起写上。和上一眼一样就写没变。")
    lines.append("仍在：是或否")
    return "\n".join(lines)


def public_catalog() -> list[dict]:
    out = []
    for kind in kinds():
        out.append({
            "id": kind.id,
            "label": kind.label,
            "scene": kind.scene,
            "configurable": kind.configurable,
            "interval": kind.interval,
            "subs": [_public_sub(sub) for sub in kind.subs],
        })
    return out


def _public_sub(sub: Sub) -> dict:
    return {
        "id": sub.id,
        "label": sub.label,
        "scene": sub.scene,
        "custom": sub.custom,
        "match": sub.match,
        "names": list(sub.names),
        "processes": list(sub.processes),
        "titles": list(sub.titles),
        "phases": [
            {
                "id": phase.id,
                "label": phase.label,
                "frames": phase.frames,
                "detail": phase.detail,
                "slots": list(phase.slots),
                "speak": phase.speak,
                "company": phase.company,
            }
            for phase in sub.phases
        ],
    }


def _load() -> tuple[Kind, ...]:
    from .builtin import kinds as builtin_kinds

    built = list(builtin_kinds())
    extra = _read_overlay()
    by_kind = {item.id: item for item in built}
    for row in extra:
        kind_id = str(row.get("kind") or "")
        kind = by_kind.get(kind_id)
        if kind is None or not kind.configurable:
            continue
        sub = _sub_from(row, kind, custom=True)
        if sub is None or kind.sub(sub.id) is not None:
            continue
        by_kind[kind_id] = Kind(
            id=kind.id,
            label=kind.label,
            scene=kind.scene,
            configurable=kind.configurable,
            interval=kind.interval,
            template=kind.template,
            subs=kind.subs + (sub,),
        )
    return tuple(by_kind[item.id] for item in built if item.id in by_kind)


def _read_overlay() -> list[dict]:
    path = overlay_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("subs") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _kind_from(raw: dict, *, custom: bool) -> Kind:
    template = tuple(_phase_from(item) for item in raw.get("template") or [] if isinstance(item, dict))
    kind = Kind(
        id=str(raw.get("id") or ""),
        label=str(raw.get("label") or ""),
        scene=str(raw.get("scene") or "unknown"),
        configurable=bool(raw.get("configurable")),
        interval=float(raw.get("interval") or 10),
        template=template,
        subs=(),
    )
    subs = []
    for row in raw.get("subs") or []:
        if isinstance(row, dict):
            sub = _sub_from(row, kind, custom=custom)
            if sub is not None:
                subs.append(sub)
    return Kind(
        id=kind.id,
        label=kind.label,
        scene=kind.scene,
        configurable=kind.configurable,
        interval=kind.interval,
        template=kind.template,
        subs=tuple(subs),
    )


def _sub_from(raw: dict, kind: Kind, *, custom: bool) -> Sub | None:
    sub_id = str(raw.get("id") or "").strip()
    label = str(raw.get("label") or "").strip()
    if not sub_id or not label:
        return None
    phases = tuple(_phase_from(item) for item in raw.get("phases") or [] if isinstance(item, dict))
    if not phases:
        phases = kind.template
    if not phases or any(not item.id or not item.label for item in phases):
        return None
    match = str(raw.get("match") or "process").strip()
    if match not in {"process", "title", "either"}:
        match = "process"
    processes = _procs(raw.get("processes"))
    titles = _words(raw.get("titles"))
    if match == "process" and not processes:
        return None
    if match == "title" and not titles:
        return None
    if match == "either" and not processes and not titles:
        return None
    hints = raw.get("process_phase") if isinstance(raw.get("process_phase"), dict) else {}
    known = {item.id for item in phases}
    return Sub(
        id=sub_id,
        label=label,
        kind=kind.id,
        scene=str(raw.get("scene") or kind.scene),
        match=match,
        names=_words(raw.get("names")),
        processes=processes,
        titles=titles,
        process_phase={str(key).lower(): str(value) for key, value in hints.items() if str(value) in known},
        phases=phases,
        custom=custom,
    )


def _phase_from(raw: dict) -> Phase:
    slots = tuple(str(item) for item in raw.get("slots") or [] if str(item).strip())
    return Phase(
        id=str(raw.get("id") or "").strip(),
        label=str(raw.get("label") or "").strip(),
        frames=max(1, int(raw.get("frames") or 1)),
        detail=bool(raw.get("detail")),
        slots=slots,
        say=str(raw.get("say") or ""),
        speak=str(raw.get("speak") or ""),
        company=str(raw.get("company") or ""),
    )


def _words(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _procs(value) -> tuple[str, ...]:
    return tuple(item.lower() for item in _words(value))
