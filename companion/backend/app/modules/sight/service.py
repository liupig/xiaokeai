"""识别体验服务。眼睛按这里给出的规格看，小可爱只使用这里交出的结果。"""
from __future__ import annotations

import json
from typing import Any

from . import catalog, session
from .model import Brief, Order


class SightError(ValueError):
    pass


def reload() -> None:
    catalog.reload()


def reset() -> None:
    session.reset()


def prepare(process: str = "", title: str = "", window: str = "") -> Order:
    return session.prepare(process, title, window)


def commit(process: str, title: str, window: str, eyes_text: str = "") -> Brief:
    return session.commit(process, title, window, eyes_text)


def current() -> Brief:
    return session.current()


def hold_name(name: str) -> bool:
    sub = catalog.find_named(name)
    if sub is None or sub.kind != "game":
        return False
    return session.hold(sub.kind, sub.id)


def release() -> None:
    session.release()


def interval() -> float | None:
    order = session.prepare()
    if not order.active or order.interval <= 0:
        return None
    return order.interval


def cue_rule() -> str:
    brief = session.current()
    if not brief.active:
        return ""
    where = "网页" if brief.surface == "web" else "客户端" if brief.surface == "client" else ""
    head = f"【识别】{brief.kind_label} / {brief.sub_label}"
    if where:
        head += f"，{where}"
    head += f"，{brief.phase_label}。"
    return head + brief.speak + brief.company


def spoken_line() -> str:
    """这一眼交给她接的那句。开口要求里要带上，不能只写在系统备注里。"""
    brief = session.current()
    if not brief.active:
        return ""
    for row in (brief.handoff or "").splitlines():
        if row.startswith("原文："):
            return row.split("：", 1)[1].strip()
    return ""


def bound_speech(instruction: str, *, line: str | None = None, rule: str | None = None) -> str:
    """开口那一句放在最后。阶段规矩写在反应要求后面，才盖得住临场发挥。"""
    rule = cue_rule() if rule is None else rule
    line = spoken_line() if line is None else line
    if not rule and not line:
        return instruction
    tail = instruction
    if rule:
        tail += "\n" + rule
    if line:
        tail += f"\n这一句：「{line}」"
    tail += "\n只接引号里已确认的内容。不要补写没看到、没听到的人物身份、动作、后续和结果。"
    return tail


def catalog_public() -> dict[str, Any]:
    return {"kinds": catalog.public_catalog(), "now": session.snapshot() | current().public()}


def add_sub(kind_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    kind = catalog.kind_of(kind_id)
    if kind is None:
        raise SightError("没有这个大类")
    if not kind.configurable:
        raise SightError("这个大类不能加子类")
    body = dict(raw)
    body["kind"] = kind.id
    body["id"] = str(body.get("id") or "").strip()
    body["label"] = str(body.get("label") or "").strip()
    if not body["id"] or not body["label"]:
        raise SightError("子类要有 id 和名字")
    if kind.sub(body["id"]) is not None:
        raise SightError("已经有这个子类")
    row = _stored_row(body)
    if catalog._sub_from(row, kind, custom=True) is None:
        raise SightError("子类缺少能对上的进程或标题")
    rows = [item for item in catalog._read_overlay() if not (item.get("kind") == kind.id and item.get("id") == row["id"])]
    rows.append(row)
    _write(rows)
    catalog.reload()
    sub = catalog.find_sub(kind.id, row["id"])
    if sub is None:
        raise SightError("子类没有写上")
    return {"id": sub.id, "kind": sub.kind, "label": sub.label}


def remove_sub(kind_id: str, sub_id: str) -> None:
    kind = catalog.kind_of(kind_id)
    sub = catalog.find_sub(kind_id, sub_id)
    if kind is None or sub is None:
        raise SightError("没有这个子类")
    if not sub.custom:
        raise SightError("内置子类不能删")
    rows = [item for item in catalog._read_overlay() if not (item.get("kind") == kind_id and item.get("id") == sub_id)]
    _write(rows)
    catalog.reload()


def _stored_row(raw: dict[str, Any]) -> dict[str, Any]:
    kept = ["kind", "id", "label", "scene", "match", "names", "processes", "titles", "phases", "process_phase"]
    return {key: raw[key] for key in kept if key in raw and raw[key] not in (None, "", [])}


def _write(rows: list[dict]) -> None:
    path = catalog.overlay_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"subs": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
