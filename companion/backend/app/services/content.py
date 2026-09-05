"""A 包指向 B 资源包：校验目录、写入 content.path。改完需重启才会换路径。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..paths import (
    CONTENT_DIR,
    CONTENT_MARKER,
    ROOT_DIR,
    content_status,
    write_content_path,
)

FAIL = "设置失败：请选资源包（B）文件夹，里面必须有 xiaoke-content.json"


def _resolve_choice(raw: str) -> Path | None:
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        return None
    p = Path(text)
    if not p.is_absolute():
        p = (ROOT_DIR / p).resolve()
    else:
        p = p.resolve()
    if p.is_file() and p.name.lower() == CONTENT_MARKER.lower():
        p = p.parent
    return p


def inspect(raw: str) -> Dict[str, Any]:
    p = _resolve_choice(raw)
    if p is None:
        return {"ok": False, "path": "", "message": FAIL}
    if not p.exists():
        return {"ok": False, "path": str(p), "message": FAIL + "（路径不存在）"}
    if p.is_file():
        return {"ok": False, "path": str(p), "message": FAIL}
    if (p / "runtime" / "python.exe").is_file() and not (p / CONTENT_MARKER).is_file():
        return {"ok": False, "path": str(p), "message": "设置失败：这是程序包（A），请选资源包（B）"}
    if not (p / CONTENT_MARKER).is_file():
        return {"ok": False, "path": str(p), "message": FAIL}
    return {"ok": True, "path": str(p), "message": "可以使用"}


def save(raw: str) -> Dict[str, Any]:
    checked = inspect(raw)
    current = content_status()
    if not checked.get("ok"):
        return {
            **current,
            "ok": False,
            "message": checked.get("message") or FAIL,
            "tried": checked.get("path") or "",
            "restart": False,
        }
    write_content_path(ROOT_DIR, Path(checked["path"]))
    same = bool(CONTENT_DIR) and Path(checked["path"]).resolve() == CONTENT_DIR.resolve()
    return {
        **content_status(),
        "ok": True,
        "path": checked["path"],
        "restart": not same,
        "message": "已记下路径。关掉窗口再打开后生效。" if not same else "已是当前资源包。",
    }
