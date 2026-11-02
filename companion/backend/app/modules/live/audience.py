"""老观众。进程内记住谁来过、谁送过，不把整场弹幕堆进提示词。"""
from __future__ import annotations

import time

from .config import feature_on
from .events import LiveEvent

_MAX = 2000


class AudienceBook:
    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def clear(self) -> None:
        self._rows.clear()

    def note(self, ev: LiveEvent, now: float | None = None) -> None:
        now = time.time() if now is None else now
        key = ev.user_key()
        row = self._rows.get(key)
        if row is None:
            row = {"name": ev.nickname, "visits": 0, "gifts": 0, "last": now, "words": ""}
            self._rows[key] = row
        row["name"] = ev.nickname or row["name"]
        row["last"] = now
        if ev.kind == "comment":
            row["visits"] = int(row["visits"]) + 1
            row["words"] = ev.content[:40]
        elif ev.kind in ("gift", "superchat", "guard"):
            row["gifts"] = int(row["gifts"]) + max(ev.count, 1)
        if len(self._rows) > _MAX:
            self._evict()

    def _evict(self) -> None:
        ranked = sorted(self._rows.items(), key=lambda item: item[1]["last"])
        for key, _row in ranked[: len(self._rows) - _MAX]:
            self._rows.pop(key, None)

    def regulars(self, cfg: dict, limit: int = 6) -> list[dict]:
        if not feature_on(cfg, "audience"):
            return []
        rows = list(self._rows.values())
        rows = [row for row in rows if row["visits"] >= 3 or row["gifts"] > 0]
        rows.sort(key=lambda row: (row["gifts"], row["visits"], row["last"]), reverse=True)
        return rows[:limit]

    def prompt(self, cfg: dict) -> str:
        rows = self.regulars(cfg)
        if not rows:
            return ""
        parts = []
        for row in rows:
            bit = f"{row['name']}（来过{row['visits']}次"
            if row["gifts"]:
                bit += f"，送过{row['gifts']}份"
            bit += "）"
            parts.append(bit)
        return "常来的人：" + "、".join(parts)
