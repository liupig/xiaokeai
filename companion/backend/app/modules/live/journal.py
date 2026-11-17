"""正式直播会话日志。只记录互动与回执，不写 Cookie、模型 Key 或个人聊天。"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class LiveJournal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = ""
        self._lock = threading.RLock()
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS live_sessions ("
                       "id TEXT PRIMARY KEY, started REAL, ended REAL, info TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS live_trace ("
                       "seq INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, at REAL, kind TEXT, data TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS ix_live_trace_session ON live_trace(session, seq)")
            db.execute("CREATE INDEX IF NOT EXISTS ix_live_sessions_started ON live_sessions(started DESC)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        try:
            with db:
                yield db
        finally:
            db.close()

    def start(self, character_id: int, room: dict) -> str:
        self.session_id = f"live-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        info = {"character_id": int(character_id or 0), "room": room, "product": "live-show-engine-v1"}
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO live_sessions(id, started, ended, info) VALUES (?, ?, 0, ?)",
                       (self.session_id, time.time(), json.dumps(info, ensure_ascii=False)))
        self.append("session_start", info)
        return self.session_id

    def append(self, kind: str, data: dict[str, Any], at: float | None = None) -> None:
        if not self.session_id:
            return
        safe = json.loads(json.dumps(data or {}, ensure_ascii=False, default=str))
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO live_trace(session, at, kind, data) VALUES (?, ?, ?, ?)",
                       (self.session_id, time.time() if at is None else float(at), kind[:32],
                        json.dumps(safe, ensure_ascii=False)))

    def end(self, reason: str = "operator") -> None:
        if not self.session_id:
            return
        self.append("session_end", {"reason": reason})
        with self._lock, self._connect() as db:
            db.execute("UPDATE live_sessions SET ended=? WHERE id=?", (time.time(), self.session_id))

    def sessions(self, limit: int = 20) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT id, started, ended, info FROM live_sessions "
                              "ORDER BY started DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [{"id": sid, "started": started, "ended": ended, **json.loads(info)}
                for sid, started, ended, info in rows]

    def trace(self, session_id: str, after: int = 0, limit: int = 500) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT seq, at, kind, data FROM live_trace "
                              "WHERE session=? AND seq>? ORDER BY seq LIMIT ?",
                              (session_id, max(0, after), max(1, min(limit, 2000)))).fetchall()
        return [{"seq": seq, "at": at, "kind": kind, "data": json.loads(data)}
                for seq, at, kind, data in rows]

    def metrics(self, session_id: str) -> dict:
        trace = self.trace(session_id, limit=2000)
        events = [row for row in trace if row["kind"] == "event"]
        turns = [row for row in trace if row["kind"] == "turn"]
        acks = [row for row in trace if row["kind"] == "ack"]
        latencies = []
        for row in turns:
            sources = row["data"].get("sources") or []
            if sources:
                first = min(float(src.get("ts") or 0) / 1000 for src in sources)
                if first > 0:
                    latencies.append(max(0.0, float(row["at"]) - first))
        outcomes: dict[str, int] = {}
        for row in acks:
            key = str(row["data"].get("outcome") or "unknown")
            outcomes[key] = outcomes.get(key, 0) + 1
        return {
            "session_id": session_id,
            "events": len(events),
            "comments": sum(row["data"].get("kind") == "comment" for row in events),
            "turns": len(turns),
            "acks": outcomes,
            "model_failures": sum(row["kind"] == "model_failure" for row in trace),
            "source_to_turn_avg_sec": round(sum(latencies) / len(latencies), 3) if latencies else 0,
            "source_to_turn_max_sec": round(max(latencies), 3) if latencies else 0,
            "trace_rows": len(trace),
        }
