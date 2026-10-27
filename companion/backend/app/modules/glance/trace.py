"""陪看调试记录。像素只给记录页，不进对话。"""
from __future__ import annotations

import base64
import threading
import time
from typing import Any

from . import archive

_MAX_HOT = 36
_lock = threading.Lock()
_rows: list[dict[str, Any]] = []


def note_look(data: dict[str, Any], pack: dict[str, Any] | None, *, ask: str = "", gate: bool = False, detail: bool = False) -> str:
    """记一眼。开关开着时，截图写入本机并留下最近三天。"""
    pack = pack or {}
    captured = _decode_list(pack.get("captured"))
    sent = _decode_list(pack.get("sent"))
    item_id = archive.allocate_id()
    row = {
        "id": item_id,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ask": (ask or "")[:80],
        "gate": bool(gate),
        "detail": bool(detail),
        "ok": bool(data.get("ok")),
        "skipped": bool(data.get("skipped")),
        "channel": str(data.get("channel") or ""),
        "downsample": str(data.get("downsample") or ""),
        "ms": int(data.get("ms") or 0),
        "frames": int(data.get("frames") or 0),
        "result": str(data.get("text") or "")[:2000],
        "message": str(data.get("message") or "")[:300],
        "prompt": str(pack.get("prompt") or "")[:4000],
        "handoff": "",
        "handoff_why": "",
        "xiaoke_in": "",
        "xiaoke_raw": "",
        "xiaoke_out": "",
        "xiaoke_action": "",
        "captured": len(captured),
        "sent": len(sent),
    }
    saved = archive.save(item_id, row, captured, sent)
    with _lock:
        hot = dict(row)
        if not saved:
            hot["_captured"] = captured
            hot["_sent"] = sent
        _rows.append(hot)
        if len(_rows) > _MAX_HOT:
            del _rows[: len(_rows) - _MAX_HOT]
    return item_id


def mark(item_id: str, **fields: Any) -> None:
    if not item_id:
        return
    allowed = {
        "handoff", "handoff_why", "xiaoke_in", "xiaoke_raw", "xiaoke_out", "xiaoke_action",
        "result", "prompt",
    }
    cleaned = {key: str(value or "")[:4000] for key, value in fields.items() if key in allowed}
    if not cleaned:
        return
    with _lock:
        for row in reversed(_rows):
            if row["id"] != item_id:
                continue
            row.update(cleaned)
            break
    archive.patch(item_id, cleaned)


def shot(item_id: str, kind: str, index: int) -> bytes | None:
    key = "_captured" if kind == "captured" else "_sent" if kind == "sent" else ""
    if not key:
        return None
    with _lock:
        for row in reversed(_rows):
            if row["id"] != item_id:
                continue
            blobs = row.get(key) or []
            if 0 <= index < len(blobs):
                return blobs[index]
            break
    return archive.image(item_id, kind, index)


def feed(limit: int = 40, before: str = "", after: str = "") -> dict[str, Any]:
    rows = _merged()
    chosen = rows
    if after:
        chosen = [row for row in rows if row["id"] > after]
    elif before:
        chosen = [row for row in rows if row["id"] < before]
    size = max(1, min(int(limit or 40), 100))
    page = chosen[:size]
    has_older = False
    if page and not after:
        last = page[-1]["id"]
        has_older = any(row["id"] < last for row in rows)
    state = archive.status()
    return {
        "items": page,
        "total": len(rows),
        "has_older": has_older,
        "keeping": state["on"],
        "packed": state["packed"],
        "days": state["days"],
    }


def clear() -> None:
    with _lock:
        _rows.clear()
    archive.wipe()


def _merged() -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in archive.rows():
        by_id[str(row.get("id") or "")] = _public(row)
    with _lock:
        for row in _rows:
            pub = _public(row)
            current = by_id.get(pub["id"])
            if current is None:
                by_id[pub["id"]] = pub
            else:
                current.update(pub)
    return sorted(by_id.values(), key=lambda row: row["id"], reverse=True)


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "at": str(row.get("at") or ""),
        "ask": str(row.get("ask") or ""),
        "gate": bool(row.get("gate")),
        "detail": bool(row.get("detail")),
        "ok": bool(row.get("ok")),
        "skipped": bool(row.get("skipped")),
        "channel": str(row.get("channel") or ""),
        "downsample": str(row.get("downsample") or ""),
        "ms": int(row.get("ms") or 0),
        "frames": int(row.get("frames") or 0),
        "result": str(row.get("result") or ""),
        "message": str(row.get("message") or ""),
        "prompt": str(row.get("prompt") or ""),
        "handoff": str(row.get("handoff") or ""),
        "handoff_why": str(row.get("handoff_why") or ""),
        "xiaoke_in": str(row.get("xiaoke_in") or ""),
        "xiaoke_raw": str(row.get("xiaoke_raw") or ""),
        "xiaoke_out": str(row.get("xiaoke_out") or ""),
        "xiaoke_action": str(row.get("xiaoke_action") or ""),
        "captured": int(row.get("captured") or 0),
        "sent": int(row.get("sent") or 0),
    }


def _decode_list(raw: Any) -> list[bytes]:
    out: list[bytes] = []
    if not isinstance(raw, list):
        return out
    for item in raw[:8]:
        text = str(item or "").strip()
        if not text:
            continue
        if "," in text and text.startswith("data:"):
            text = text.split(",", 1)[1]
        try:
            blob = base64.b64decode(text, validate=False)
        except Exception:
            continue
        if blob:
            out.append(blob)
    return out
