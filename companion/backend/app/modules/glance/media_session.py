"""Read current Windows media sessions, scoped to the selected player/window."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading
import time

_lock = threading.Lock()
_at = 0.0
_rows: list[dict] = []


def choose(rows: list[dict], desk) -> dict:
    process = desk.process.lower().removesuffix(".exe")
    if not process:
        return {}
    matches = [r for r in rows if process in str(r.get("app") or "").lower()]
    if process in {"chrome", "msedge", "firefox", "brave"}:
        # A browser can have several sessions; another tab's audio is not proof.
        matches = [r for r in matches if r.get("title") and str(r["title"]).lower() in
                   f"{desk.title} {desk.window}".lower()]
    if len(matches) != 1:
        return {}
    return dict(matches[0])


def latest(desk) -> dict:
    global _at, _rows
    if os.name != "nt":
        return {}
    with _lock:
        if time.monotonic() - _at >= 3:
            _at = time.monotonic()
            try:
                result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                    str(Path(__file__).with_suffix(".ps1"))], capture_output=True,
                    timeout=2, creationflags=subprocess.CREATE_NO_WINDOW)
                data = json.loads(result.stdout.decode("utf-8-sig")) if result.returncode == 0 else []
                _rows = data if isinstance(data, list) else [data]
            except (OSError, ValueError, subprocess.TimeoutExpired):
                _rows = []
        return choose(_rows, desk)
