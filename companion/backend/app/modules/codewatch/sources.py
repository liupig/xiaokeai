"""本机编程助手：Cursor / Codex / Claude Code + 国内前三。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

SOURCE_IDS = ("cursor", "codex", "cc", "lingma", "trae", "comate")

CATALOG: Tuple[Dict[str, str], ...] = (
    {"id": "cursor", "label": "Cursor", "short": "Cursor"},
    {"id": "codex", "label": "Codex", "short": "Codex"},
    {"id": "cc", "label": "Claude Code", "short": "CC"},
    {"id": "lingma", "label": "通义灵码", "short": "灵码"},
    {"id": "trae", "label": "Trae", "short": "Trae"},
    {"id": "comate", "label": "文心快码", "short": "快码"},
)

_LABEL = {row["id"]: row["label"] for row in CATALOG}


def label_of(sid: str) -> str:
    return _LABEL.get(sid, sid or "Cursor")


def _home() -> Path:
    return Path.home()


def _roaming() -> Path:
    raw = os.environ.get("APPDATA")
    return Path(raw) if raw else _home() / "AppData" / "Roaming"


def _local() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    return Path(raw) if raw else _home() / "AppData" / "Local"


def _homes(sid: str) -> List[Path]:
    h, r, loc = _home(), _roaming(), _local()
    if sid == "cursor":
        return [h / ".cursor"]
    if sid == "codex":
        return [h / ".codex", r / "Codex"]
    if sid == "cc":
        return [h / ".claude", r / "claude-code-desktop", loc / "claude-cli-nodejs"]
    if sid == "lingma":
        return [
            h / ".lingma",
            r / "Lingma",
            r / "alibaba-lingma",
            loc / "Lingma",
            r / "Code" / "User" / "globalStorage" / "alibabacloud-tools.tongyi-lingma",
        ]
    if sid == "trae":
        return [h / ".trae", r / "Trae", r / "Trae CN", loc / "Trae"]
    if sid == "comate":
        return [
            h / ".comate",
            r / "BaiduComate",
            r / "comate",
            r / "Code" / "User" / "globalStorage" / "baidu.baidu-comate",
        ]
    return []


def homes(sid: str) -> List[Path]:
    return [p for p in _homes(sid) if p.is_dir()]


def probe() -> Dict[str, bool]:
    return {sid: bool(homes(sid)) for sid in SOURCE_IDS}


def jsonl_roots(sid: str) -> List[Path]:
    found: List[Path] = []
    if sid == "cursor":
        p = _home() / ".cursor" / "projects"
        return [p] if p.is_dir() else []
    if sid == "cc":
        for root in homes(sid):
            proj = root / "projects"
            found.append(proj if proj.is_dir() else root)
        return found
    if sid == "codex":
        for root in homes(sid):
            for name in ("sessions", "history", "transcripts"):
                p = root / name
                found.append(p if p.is_dir() else root)
        return found
    if sid in ("lingma", "comate"):
        return homes(sid)
    return []


def growth_files(sid: str) -> List[Path]:
    """体积变化就能说明在干活的文件，不扫整棵缓存树。"""
    out: List[Path] = []
    if sid == "trae":
        for root in homes(sid):
            wal = root / "ModularData" / "ai-agent" / "database.db-wal"
            if wal.is_file():
                out.append(wal)
            logs = root / "logs"
            if logs.is_dir():
                out.extend(_newest(logs, "ai-agent", ".log", 6))
        return out
    if sid in ("lingma", "comate", "codex"):
        for root in homes(sid):
            out.extend(_newest(root, "", ".jsonl", 8))
            out.extend(_newest(root, "", ".log", 4))
    return out


def iter_jsonl(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    skip = {
        "cache", "cacheddata", "gpucache", "code cache", "logs",
        "blob_storage", "crashpad", "node_modules",
    }
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in skip]
            rel = Path(dirpath).relative_to(root)
            if len(rel.parts) > 6:
                dirnames[:] = []
                continue
            for name in filenames:
                if name.endswith(".jsonl"):
                    yield Path(dirpath) / name
    except OSError:
        return


def _newest(root: Path, needle: str, suffix: str, limit: int) -> List[Path]:
    hits: List[Path] = []
    skip = {"cache", "cacheddata", "gpucache", "node_modules", "crashpad"}
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in skip]
            if len(Path(dirpath).relative_to(root).parts) > 5:
                dirnames[:] = []
                continue
            for name in filenames:
                if not name.endswith(suffix):
                    continue
                if needle and needle not in name.lower():
                    continue
                hits.append(Path(dirpath) / name)
    except OSError:
        return []
    hits.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return hits[:limit]
