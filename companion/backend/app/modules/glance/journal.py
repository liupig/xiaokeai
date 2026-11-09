"""连续陪看的话题、情绪与话头视图。"""
from __future__ import annotations

import re
import threading
import time


class Journal:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.key = ""
        self.beats: list[str] = []
        self.speeches: list[dict] = []
        self.reactions: list[dict] = []
        self.highlights: list[dict] = []
        self.open_loops: list[dict] = []
        self.mood = "平静"
        self.mood_cause = ""
        self.mood_at = 0.0
        self.user_at = time.time()
        self.company_at = 0.0
        self.previous: dict = {}
        self.opened = False

    def reset(self) -> None:
        with self._lock:
            self.key = ""
            self.beats.clear()
            self.speeches.clear()
            self.reactions.clear()
            self.highlights.clear()
            self.open_loops.clear()
            self.mood = "平静"
            self.mood_cause = ""
            self.mood_at = 0.0
            self.user_at = time.time()
            self.company_at = 0.0
            self.previous = {}
            self.opened = False

    def bind(self, key: str) -> None:
        key = (key or "").strip()
        if not key:
            return
        with self._lock:
            if key == self.key:
                return
            previous_key = self.key
            payload = self._snapshot_locked()
        if previous_key:
            from .archive import save_journal
            save_journal(previous_key, payload)
        from .archive import load_journal
        previous = load_journal(key)
        with self._lock:
            self.key = key
            self.beats.clear()
            self.speeches.clear()
            self.reactions.clear()
            self.open_loops.clear()
            self.highlights.clear()
            self.mood = "平静"
            self.mood_cause = ""
            self.mood_at = 0.0
            self.previous = previous
            self.opened = False

    def note_observation(self, text: str) -> None:
        found = []
        for raw in (text or "").splitlines():
            line = raw.strip()
            if not line or line.startswith(("标题：", "界面：", "窗口：")):
                continue
            value = line.split("：", 1)[1].strip() if "：" in line else line
            if len(value) < 4 or re.search(r"光柱|手没动|标题更新|没变|持续出现|一直亮", value):
                continue
            if value not in found:
                found.append(value)
        if not found:
            return
        with self._lock:
            for value in found:
                if value not in self.beats:
                    self.beats.append(value[:180])
            del self.beats[:-12]

    def note_user(self, text: str) -> None:
        spoken = " ".join((text or "").split())[:80]
        if not spoken:
            return
        with self._lock:
            self.reactions.append({"text": spoken, "at": time.time()})
            del self.reactions[:-10]
            self.user_at = time.time()
            if len(spoken) >= 2:
                self.open_loops.clear()

    def note_speech(self, text: str, *, mood: str = "平静", cause: str = "", kind: str = "reaction") -> None:
        spoken = " ".join((text or "").split())[:120]
        if not spoken:
            return
        now = time.time()
        with self._lock:
            row = {"text": spoken, "mood": mood, "cause": cause[:180], "at": now, "kind": kind}
            self.speeches.append(row)
            del self.speeches[:-20]
            self.mood = mood
            self.mood_cause = cause[:180]
            self.mood_at = now
            if kind == "company":
                self.company_at = now
            if "?" in spoken or "？" in spoken:
                self.open_loops.append(row)
                del self.open_loops[:-2]
            if mood in {"搞笑", "悲伤", "燃"} and kind == "reaction":
                self.highlights.append(row)
                self.highlights = self.highlights[-3:]
            self.previous = {}

    def opening(self) -> str:
        with self._lock:
            if self.opened or not self.previous:
                return ""
            self.opened = True
            rows = self.previous.get("speeches") or []
            last = rows[-1]["text"] if rows else ""
            mood = str(self.previous.get("mood") or "平静")
            return f"我们上次一起看过这个。上次最后你说：「{last}」，当时情绪是{mood}。" if last else "我们上次一起看过这个。"

    def recent_lines(self, limit: int = 6) -> list[str]:
        with self._lock:
            current = [str(row.get("text") or "") for row in self.speeches[-limit:]]
            previous = [str(row.get("text") or "") for row in (self.previous.get("speeches") or [])[-limit:]]
        return [text for text in previous + current if text]

    def view(self, situation=None, timeline=None) -> str:
        with self._lock:
            beats = list(self.beats[-4:])
            speeches = list(self.speeches[-1:])
            reactions = list(self.reactions[-2:])
            loops = list(self.open_loops)
            highlights = list(self.highlights[-3:])
            mood, cause, mood_at = self.mood, self.mood_cause, self.mood_at
            previous = dict(self.previous)
        lines = []
        if situation is not None:
            lines.append(f"场景：{situation.scene}；对象：{situation.title or situation.object_id or '当前内容'}")
        if beats:
            lines.append("最近内容发展（可用于接着聊，不要只描述最后一帧）：" + " → ".join(beats))
        elif timeline is not None:
            recent = timeline.context(time.time())
            if recent:
                lines.append(recent[-600:])
        for row in speeches:
            lines.append(f"她刚才已说过，避免重复：{row['text']}")
        for row in reactions:
            lines.append(f"他刚才：{row['text']}")
        if mood_at:
            if time.time() - mood_at > 180:
                mood, cause = "平静", "刚才的情绪已回落"
            lines.append(f"当前情绪：{mood}；起因：{cause or '刚才的内容'}")
        for row in loops:
            lines.append(f"没接上的话头：{row['text']}")
        for row in highlights:
            lines.append(f"高光：{row['text']}")
        if previous:
            lines.append("上次同内容的记忆已载入，只有自然时才提起，不要编造上次细节。")
        return "\n".join(lines)[:1400]

    def save(self) -> None:
        with self._lock:
            if not self.key:
                return
            key, payload = self.key, self._snapshot_locked()
        from .archive import save_journal
        save_journal(key, payload)

    def _snapshot_locked(self) -> dict:
        return {
            "beats": list(self.beats[-8:]),
            "speeches": list(self.speeches[-6:]),
            "reactions": list(self.reactions[-4:]),
            "highlights": list(self.highlights[-3:]),
            "mood": self.mood,
            "mood_cause": self.mood_cause,
            "mood_at": self.mood_at,
            "saved_at": time.time(),
        }


journal = Journal()
