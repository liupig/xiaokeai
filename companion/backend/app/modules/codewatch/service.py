"""Code 伴侣状态机。started / working / done 是给舞台的节拍，idle 是静默。"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .sources import CATALOG, SOURCE_IDS, probe

Listener = Callable[[Dict[str, Any]], None]

PHASES = ("idle", "started", "working", "done")
SOURCES = SOURCE_IDS

# 开工先停一会儿再进「进行中」，别跟开口叠在一起。
START_HOLD_SEC = 16.0
# transcript 不再增长，视为这轮写完。
DONE_IDLE_SEC = 16.0
# 完成后过多久回到空闲，避免牌子先收了她还没说完。
DONE_HOLD_SEC = 36.0
# 同一轮里 started 去抖。
STARTED_GAP_SEC = 2.0


class CodewatchBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: List[Listener] = []
        self._watching = False
        self._phase = "idle"
        self._source = "cursor"
        self._title = ""
        self._project = ""
        self._tool = ""
        self._tools: List[str] = []
        self._hint = ""
        self._seq = 0
        self._changed_at = 0.0
        self._started_at = 0.0
        self._last_started_at = 0.0
        self._cursor_found = False
        self._found: Dict[str, bool] = {sid: False for sid in SOURCE_IDS}
        self._enabled: List[str] = ["cursor"]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snap_unlocked()

    def _snap_unlocked(self) -> Dict[str, Any]:
        return {
            "watching": self._watching,
            "phase": self._phase,
            "source": self._source,
            "title": self._title,
            "project": self._project,
            "tool": self._tool,
            "tools": list(self._tools),
            "hint": self._hint,
            "seq": self._seq,
            "changed_at": self._changed_at,
            "cursor_found": self._cursor_found or bool(self._found.get("cursor")),
            "sources": [
                {
                    "id": row["id"],
                    "label": row["label"],
                    "short": row["short"],
                    "found": bool(self._found.get(row["id"])),
                    "on": row["id"] in self._enabled,
                    "active": self._phase != "idle" and self._source == row["id"],
                }
                for row in CATALOG
            ],
            "enabled": list(self._enabled),
        }

    def set_watching(self, on: bool) -> Dict[str, Any]:
        with self._lock:
            self._watching = bool(on)
            if not on:
                self._phase = "idle"
                self._title = ""
                self._project = ""
                self._tool = ""
                self._tools = []
                self._hint = ""
                self._changed_at = time.time()
                self._seq += 1
                snap = self._snap_unlocked()
            else:
                self._found = {sid: bool(probe().get(sid)) for sid in SOURCE_IDS}
                self._cursor_found = bool(self._found.get("cursor"))
                snap = self._snap_unlocked()
        self._emit(snap)
        return snap

    def set_cursor_found(self, found: bool) -> None:
        self.set_found("cursor", found)

    def set_found(self, sid: str, found: bool) -> None:
        if sid not in SOURCE_IDS:
            return
        with self._lock:
            if self._found.get(sid) == found:
                return
            self._found[sid] = bool(found)
            if sid == "cursor":
                self._cursor_found = bool(found)

    def refresh_found(self) -> None:
        hit = probe()
        with self._lock:
            self._found = {sid: bool(hit.get(sid)) for sid in SOURCE_IDS}
            self._cursor_found = bool(self._found.get("cursor"))

    def set_enabled(self, ids: Optional[List[str]]) -> None:
        picked = [sid for sid in (ids or []) if sid in SOURCE_IDS]
        if not picked:
            picked = ["cursor"]
        with self._lock:
            self._enabled = picked

    def enabled(self) -> List[str]:
        with self._lock:
            return list(self._enabled)

    def subscribe(self, fn: Listener) -> None:
        with self._lock:
            if fn not in self._listeners:
                self._listeners.append(fn)

    def unsubscribe(self, fn: Listener) -> None:
        with self._lock:
            if fn in self._listeners:
                self._listeners.remove(fn)

    def note(self, phase: str, *, source: str = "cursor", title: str = "",
             project: str = "", tool: str = "", hint: str = "",
             force: bool = False) -> Optional[Dict[str, Any]]:
        if phase not in PHASES:
            return None
        if source not in SOURCE_IDS:
            source = "cursor"
        now = time.time()
        with self._lock:
            if not self._watching:
                return None
            if source not in self._enabled:
                return None
            if phase == "started":
                if self._phase == "started" and (now - self._last_started_at) < STARTED_GAP_SEC and not force:
                    return None
                self._last_started_at = now
                self._started_at = now
                self._tools = []
            if phase == "working" and self._phase == "started" and not force:
                if (now - self._started_at) < START_HOLD_SEC:
                    if tool:
                        name = _clip(tool, 32)
                        if name and name not in self._tools:
                            self._tools.append(name)
                            if len(self._tools) > 8:
                                self._tools = self._tools[-8:]
                        if name:
                            self._tool = name
                    if title:
                        self._title = _clip(title, 72)
                    if project:
                        self._project = _clip(project, 48)
                    return None
            if phase == "working" and self._phase == "done" and not force:
                return None
            if phase == "working" and self._phase == "working" and not force:
                if tool:
                    name = _clip(tool, 32)
                    if name and name not in self._tools:
                        self._tools.append(name)
                        if len(self._tools) > 8:
                            self._tools = self._tools[-8:]
                    if name and name != self._tool:
                        self._tool = name
                        self._changed_at = now
                        if title:
                            self._title = _clip(title, 72)
                        if project:
                            self._project = _clip(project, 48)
                return None
            if phase == self._phase and not force:
                return None
            if phase == "done" and self._phase in ("idle", "done") and not force:
                return None
            if phase == "idle" and self._phase == "idle":
                return None
            self._phase = phase
            self._source = source
            if title:
                self._title = _clip(title, 72)
            if project:
                self._project = _clip(project, 48)
            if tool:
                name = _clip(tool, 32)
                self._tool = name
                if name and name not in self._tools:
                    self._tools.append(name)
                    if len(self._tools) > 8:
                        self._tools = self._tools[-8:]
            elif phase == "idle":
                self._tool = ""
                self._tools = []
            if hint:
                self._hint = hint
            elif phase == "started":
                self._hint = "新活来了"
            elif phase == "working":
                self._hint = "还在写"
            elif phase == "done":
                self._hint = "这轮完了"
            else:
                self._hint = ""
            self._changed_at = now
            self._seq += 1
            snap = self._snap_unlocked()
        self._emit(snap)
        return snap

    def tick(self) -> None:
        """由监视线程调用：开工稍后进入进行中，写完后回空闲。"""
        now = time.time()
        with self._lock:
            if not self._watching:
                return
            phase = self._phase
            changed = self._changed_at
            started = self._started_at
            source = self._source
        if phase == "started" and (now - started) >= START_HOLD_SEC:
            self.note("working", source=source, hint="盯着")
        elif phase == "done" and (now - changed) >= DONE_HOLD_SEC:
            self.note("idle", source=source)

    def _emit(self, snap: Dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(snap)
            except Exception:
                pass


def _clip(text: str, n: int) -> str:
    s = " ".join((text or "").split())
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


bus = CodewatchBus()
