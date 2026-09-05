"""盯各家本机痕迹。不读历史，只看监视开始之后的新行 / 体积变化。"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from .service import DONE_IDLE_SEC, bus
from .sources import SOURCE_IDS, growth_files, homes, iter_jsonl, jsonl_roots, probe

def cursor_home_ok() -> bool:
    return bool(homes("cursor"))

_USER_Q = re.compile(r"<user_query>\s*([\s\S]*?)\s*</user_query>", re.I)
_POLL = 1.2
_SKIP_TYPES = {
    "session-meta", "file-history-snapshot", "system", "progress",
    "keep", "ping", "meta",
}


class DeskWatch:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._files: Dict[str, Tuple[int, str]] = {}
        self._sizes: Dict[str, int] = {}
        self._last_activity = 0.0
        self._armed = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._files.clear()
        self._sizes.clear()
        self._armed = False
        self._last_activity = 0.0
        bus.refresh_found()
        self._thread = threading.Thread(target=self._loop, name="codewatch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        self._thread = None
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.5)

    def _loop(self) -> None:
        self._snapshot()
        self._armed = True
        while not self._stop.wait(_POLL):
            hit = probe()
            for sid, ok in hit.items():
                bus.set_found(sid, ok)
            self._scan_jsonl()
            self._scan_growth()
            bus.tick()
            self._maybe_done()

    def _active(self) -> list[str]:
        return bus.enabled() or ["cursor"]

    def _snapshot(self) -> None:
        for sid in self._active():
            for root in jsonl_roots(sid):
                for path in iter_jsonl(root):
                    if not _keep_jsonl(sid, path):
                        continue
                    try:
                        self._files[str(path)] = (path.stat().st_size, "")
                    except OSError:
                        continue
            for path in growth_files(sid):
                try:
                    self._sizes[str(path)] = path.stat().st_size
                except OSError:
                    continue

    def _scan_jsonl(self) -> None:
        seen = set()
        for sid in self._active():
            for root in jsonl_roots(sid):
                for path in iter_jsonl(root):
                    if not _keep_jsonl(sid, path):
                        continue
                    key = str(path)
                    seen.add(key)
                    self._read_jsonl(path, sid)
        for gone in [k for k in self._files if k not in seen]:
            self._files.pop(gone, None)

    def _read_jsonl(self, path: Path, sid: str) -> None:
        key = str(path)
        try:
            size = path.stat().st_size
        except OSError:
            return
        prev, buf = self._files.get(key, (0, ""))
        if size < prev:
            prev, buf = 0, ""
        if size == prev:
            return
        try:
            with path.open("rb") as fh:
                fh.seek(prev)
                chunk = fh.read(size - prev)
        except OSError:
            return
        text = buf + chunk.decode("utf-8", errors="ignore")
        lines = text.splitlines(keepends=True)
        remain = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            remain = lines.pop()
        self._files[key] = (size, remain)
        if not self._armed:
            return
        project = _project_name(path)
        sub = "subagents" in path.parts
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            self._ingest_line(line, sid, project, sub)

    def _scan_growth(self) -> None:
        if not self._armed:
            return
        for sid in self._active():
            for path in growth_files(sid):
                key = str(path)
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                prev = self._sizes.get(key)
                self._sizes[key] = size
                if prev is None or size <= prev:
                    continue
                self._last_activity = time.time()
                phase = "started" if bus.snapshot().get("phase") in ("idle", "done") else "working"
                bus.note(phase, source=sid, title="", project="", hint="还在写" if phase == "working" else "新活来了")

    def _ingest_line(self, raw: str, sid: str, project: str, sub: bool) -> None:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(obj, dict):
            return
        kind = str(obj.get("type") or obj.get("kind") or "").lower()
        if kind in _SKIP_TYPES:
            return
        role, tools, title = _read_line(obj)
        self._last_activity = time.time()
        if role == "user" and not sub:
            bus.note("started", source=sid, title=title, project=project, hint="新活来了")
            return
        tool = tools[0] if tools else ""
        bus.note("working", source=sid, title=title, project=project, tool=tool)

    def _maybe_done(self) -> None:
        snap = bus.snapshot()
        if snap.get("phase") not in ("started", "working"):
            return
        if self._last_activity <= 0:
            return
        if (time.time() - self._last_activity) < DONE_IDLE_SEC:
            return
        bus.note("done", source=str(snap.get("source") or "cursor"), hint="这轮完了")


def _keep_jsonl(sid: str, path: Path) -> bool:
    if sid == "cursor":
        return "agent-transcripts" in path.parts
    if sid == "cc":
        return "projects" in path.parts
    return True


def _project_name(path: Path) -> str:
    parts = list(path.parts)
    for key in ("projects", "sessions"):
        if key in parts:
            i = parts.index(key)
            if i + 1 < len(parts):
                return parts[i + 1]
    return path.parent.name


def _read_line(obj: dict) -> tuple[str, list[str], str]:
    role = str(obj.get("role") or "").lower()
    kind = str(obj.get("type") or "").lower()
    if not role and kind in ("user", "human"):
        role = "user"
    elif not role and kind in ("assistant", "tool", "tool_use", "tool_result"):
        role = "assistant"
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
    if not role:
        role = str(msg.get("role") or "").lower()
    content = obj.get("content")
    if content is None:
        content = msg.get("content")
    texts: list[str] = []
    tools: list[str] = []
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            part_kind = str(part.get("type") or "")
            if part_kind == "text":
                texts.append(str(part.get("text") or ""))
            elif part_kind in ("tool_use", "tool_result"):
                tools.append(str(part.get("name") or part.get("toolName") or "tool"))
    elif isinstance(content, str):
        texts.append(content)
    prompt = obj.get("prompt") or obj.get("text") or obj.get("query")
    if isinstance(prompt, str) and prompt.strip():
        texts.append(prompt)
        if not role:
            role = "user"
    title = ""
    if role == "user":
        title = _user_title("".join(texts))
    return role, tools, title


def _user_title(text: str) -> str:
    m = _USER_Q.search(text or "")
    body = (m.group(1) if m else text) or ""
    body = re.sub(r"<[^>]+>", " ", body)
    return " ".join(body.split())


watch = DeskWatch()
