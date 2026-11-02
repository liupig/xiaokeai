"""彩排收据。入站、选题、播报确认分别落盘，不存模型配置和密钥。"""
from __future__ import annotations

import json
import sqlite3
import time
import threading
from contextlib import contextmanager
from pathlib import Path


class LabJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._local = threading.local()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS live_lab_runs (id TEXT PRIMARY KEY, created REAL, info TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS live_lab_trace (seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT, at REAL, kind TEXT, data TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS live_lab_trace_run ON live_lab_trace(run, seq)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def start(self, run: str, info: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO live_lab_runs VALUES (?, ?, ?)", (run, time.time(), json.dumps(info, ensure_ascii=False)))

    def append(self, run: str, kind: str, data: dict, at: float) -> None:
        row = (run, at, kind, json.dumps(data, ensure_ascii=False))
        transaction = getattr(self._local, "transaction", None)
        if transaction is not None:
            transaction.execute("INSERT INTO live_lab_trace(run, at, kind, data) VALUES (?, ?, ?, ?)", row)
            return
        with self.connect() as db:
            db.execute("INSERT INTO live_lab_trace(run, at, kind, data) VALUES (?, ?, ?, ?)", row)

    @contextmanager
    def batch(self):
        with self.connect() as db:
            self._local.transaction = db
            try:
                yield
            finally:
                self._local.transaction = None

    def read(self, run: str, after: int = 0) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT seq, at, kind, data FROM live_lab_trace WHERE run=? AND seq>? ORDER BY seq", (run, after)).fetchall()
        return [{"seq": seq, "at": at, "kind": kind, "data": json.loads(data)} for seq, at, kind, data in rows]

    def info(self, run: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT created, info FROM live_lab_runs WHERE id=?", (run,)).fetchone()
        if row is None:
            raise KeyError(run)
        return {"run_id": run, "created": row[0], **json.loads(row[1])}

    def history(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id FROM live_lab_runs ORDER BY created DESC LIMIT 20").fetchall()
        return [self.info(row[0]) for row in rows]

    def update_info(self, run: str, patch: dict) -> None:
        info = self.info(run)
        info.pop("run_id", None)
        info.pop("created", None)
        info.update(patch)
        with self.connect() as db:
            db.execute("UPDATE live_lab_runs SET info=? WHERE id=?", (json.dumps(info, ensure_ascii=False), run))
