"""陪看截图落在本机，只留最近三天。

本地测试默认开，打包默认关。开关写在 glance-lab/keep.json，有文件就以文件为准。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ...paths import DATA_DIR, is_packed

DAYS = 3
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID = re.compile(r"^g\d{17}-\d{4}$")
_FIELDS = {
    "handoff", "handoff_why", "xiaoke_in", "xiaoke_raw", "xiaoke_out", "xiaoke_action",
    "result", "prompt",
}

_lock = threading.Lock()
_root = DATA_DIR / "glance-lab"
_rows: list[dict[str, Any]] | None = None
_seq = 0
_packed_override: bool | None = None


def bind(root: Path, *, packed: bool | None = None) -> None:
    """测试时换一个目录。正式运行不要调。"""
    global _root, _rows, _seq, _packed_override
    with _lock:
        _root = root
        _rows = None
        _seq = 0
        _packed_override = packed


def _packed() -> bool:
    if _packed_override is not None:
        return _packed_override
    return is_packed()


def keeping() -> bool:
    raw = _read_keep()
    if raw is None:
        return not _packed()
    return bool(raw.get("on"))


def set_keeping(on: bool) -> None:
    _root.mkdir(parents=True, exist_ok=True)
    (_root / "keep.json").write_text(
        json.dumps({"on": bool(on)}, ensure_ascii=False),
        encoding="utf-8",
    )


def status() -> dict[str, Any]:
    return {"on": keeping(), "packed": _packed(), "days": DAYS}


def lab_url() -> str:
    backend = (os.environ.get("COMPANION_BACKEND") or "").strip().rstrip("/")
    if backend:
        return backend + "/lab/watch"
    port = 5201 if _packed() else 8600
    return f"http://127.0.0.1:{port}/lab/watch"


def allocate_id() -> str:
    global _seq
    with _lock:
        _seq += 1
        seq = _seq
    ms = int((time.time() % 1) * 1000)
    return time.strftime("g%Y%m%d%H%M%S") + f"{ms:03d}-{seq:04d}"


def save(item_id: str, row: dict[str, Any], captured: list[bytes], sent: list[bytes]) -> bool:
    if not _ID.match(item_id) or not keeping():
        return False
    try:
        prune()
        day = _root / _day(item_id)
        day.mkdir(parents=True, exist_ok=True)
        stored = dict(row)
        stored["id"] = item_id
        stored["captured"] = _write_images(day, item_id, "c", captured)
        stored["sent"] = _write_images(day, item_id, "s", sent)
        _write_json(day / f"{item_id}.json", stored)
    except OSError:
        return False
    with _lock:
        if _rows is not None and not any(row.get("id") == item_id for row in _rows):
            _rows.append(stored)
    return True


def patch(item_id: str, fields: dict[str, Any]) -> None:
    if not _ID.match(item_id):
        return
    path = _meta(item_id)
    if path is None or not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    for key, value in fields.items():
        if key in _FIELDS:
            data[key] = str(value or "")[:4000]
    try:
        _write_json(path, data)
    except OSError:
        return
    with _lock:
        if _rows is None:
            return
        for row in _rows:
            if row.get("id") == item_id:
                row.update(data)
                return


def image(item_id: str, kind: str, index: int) -> bytes | None:
    if not _ID.match(item_id) or index < 0 or index > 7:
        return None
    letter = "c" if kind == "captured" else "s" if kind == "sent" else ""
    if not letter:
        return None
    day = _root / _day(item_id)
    path = day / f"{item_id}-{letter}{index}.jpg"
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    return blob or None


def rows() -> list[dict[str, Any]]:
    global _rows
    with _lock:
        cached = _rows
    if cached is None:
        loaded = _scan()
        with _lock:
            if _rows is None:
                _rows = loaded
            else:
                have = {str(row.get("id") or "") for row in _rows}
                for row in loaded:
                    if str(row.get("id") or "") not in have:
                        _rows.append(row)
                _rows.sort(key=lambda row: str(row.get("id") or ""))
            cached = _rows
    return [dict(row) for row in cached]


def wipe() -> None:
    global _rows
    with _lock:
        _rows = []
        root = _root
    if not root.is_dir():
        return
    for child in list(root.iterdir()):
        if child.is_dir() and _DAY.match(child.name):
            shutil.rmtree(child, ignore_errors=True)


def prune() -> None:
    global _rows
    if not _root.is_dir():
        return
    keep = _live_days()
    for child in list(_root.iterdir()):
        if child.is_dir() and _DAY.match(child.name) and child.name not in keep:
            shutil.rmtree(child, ignore_errors=True)
    with _lock:
        if _rows is not None:
            _rows = [row for row in _rows if _day(str(row.get("id") or "")) in keep]


def _live_days() -> set[str]:
    today = date.today()
    return {(today - timedelta(days=offset)).isoformat() for offset in range(DAYS)}


def _day(item_id: str) -> str:
    raw = item_id[1:9]
    if len(raw) != 8 or not raw.isdigit():
        return ""
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"


def _meta(item_id: str) -> Path | None:
    day = _day(item_id)
    if not day:
        return None
    return _root / day / f"{item_id}.json"


def _read_keep() -> dict[str, Any] | None:
    path = _root / "keep.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _scan() -> list[dict[str, Any]]:
    prune()
    found: list[dict[str, Any]] = []
    if not _root.is_dir():
        return found
    for day in sorted(p for p in _root.iterdir() if p.is_dir() and _DAY.match(p.name)):
        for path in sorted(day.glob("g*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and _ID.match(str(data.get("id") or "")):
                found.append(data)
    found.sort(key=lambda row: str(row.get("id") or ""))
    return found


def _write_images(day: Path, item_id: str, letter: str, blobs: list[bytes]) -> int:
    count = 0
    for blob in blobs[:8]:
        if not blob:
            continue
        (day / f"{item_id}-{letter}{count}.jpg").write_bytes(blob)
        count += 1
    return count


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
