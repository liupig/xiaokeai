"""Bounded, source-scoped media evidence. No pixels or generated dialogue."""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass


@dataclass
class Moment:
    start: float
    end: float
    visual: str = ""
    subtitle: str = ""
    audio: str = ""
    transition: str = ""


class MediaTimeline:
    def __init__(self, seconds: float = 24, capacity: int = 16):
        self.seconds = seconds
        self.capacity = capacity
        self._lock = threading.Lock()
        self._source = ""
        self._epoch = 0
        self._moments: list[Moment] = []
        self._cut_at = 0.0

    def reset(self) -> None:
        with self._lock:
            self._source = ""
            self._epoch += 1
            self._moments.clear()
            self._cut_at = 0.0

    def bind(self, source: str) -> int:
        with self._lock:
            if source != self._source:
                self._source = source
                self._epoch += 1
                self._moments.clear()
                self._cut_at = 0.0
            return self._epoch

    def current(self, epoch: int, at: float | None = None) -> bool:
        with self._lock:
            return epoch == self._epoch and (at is None or at >= self._cut_at)

    def cut(self, at: float = 0.0) -> None:
        with self._lock:
            self._moments.clear()
            self._cut_at = at

    def add(self, moment: Moment, *, epoch: int, now: float) -> None:
        with self._lock:
            self._prune(now)
            if epoch != self._epoch or not self._source:
                return
            if not (now - self.seconds <= moment.end <= now + 1) or moment.start > moment.end:
                return
            if moment.start < self._cut_at:
                return
            if not any((moment.visual, moment.subtitle, moment.audio, moment.transition)):
                return
            # Do not turn repeated OCR/ASR polling into new evidence or refresh
            # an old capture's timestamp. New evidence after a gap remains valid.
            signature = (moment.visual, moment.subtitle, moment.audio, moment.transition)
            if self._moments:
                last = self._moments[-1]
                if (last.visual, last.subtitle, last.audio, last.transition) == signature:
                    return
            if moment in self._moments:
                return
            self._moments.append(moment)
            self._moments.sort(key=lambda item: (item.end, item.start))
            self._moments = self._moments[-self.capacity:]

    def _prune(self, now: float) -> None:
        self._moments = [m for m in self._moments if now - self.seconds <= m.end <= now + 1]

    def rows(self, now: float) -> list[dict]:
        with self._lock:
            self._prune(now)
            return [asdict(m) for m in self._moments]

    def context(self, now: float) -> str:
        rows = self.rows(now)
        if not rows:
            return ""
        lines = ["【最近媒体片段，按采集时间先后】",
                 "以下是观察记录，旧片段不是当前画面。字幕和音频分开记录，不据此猜说话人或未观察到的因果。"]
        entries = []
        for row in rows:
            age = max(0, now - row["end"])
            duration = max(0, row["end"] - row["start"])
            parts = [f"{age:.1f}秒前" + (f"，片段长{duration:.1f}秒" if duration >= .5 else "")]
            for key, label in (("visual", "画面"), ("transition", "片段变化"), ("subtitle", "字幕原文"), ("audio", "音频转写")):
                if row[key]:
                    parts.append(f"{label}：{row[key][:180]}")
            entries.append(" | ".join(parts))
        # Keep the most recent evidence of every modality before spending the
        # remaining budget on history. Frequent OCR must not evict the picture.
        priority = set()
        for key in ("visual", "subtitle", "audio", "transition"):
            found = next((i for i in range(len(rows)-1, -1, -1) if rows[i][key]), None)
            if found is not None:
                priority.add(found)
        chosen = set()
        budget = 1600 - sum(len(line) + 1 for line in lines)
        for i in sorted(priority, reverse=True) + [i for i in range(len(rows)-1, -1, -1) if i not in priority]:
            if len(entries[i]) + 1 <= budget:
                chosen.add(i)
                budget -= len(entries[i]) + 1
        return "\n".join(lines + [entries[i] for i in sorted(chosen)])


timeline = MediaTimeline()
