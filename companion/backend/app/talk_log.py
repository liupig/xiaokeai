"""对话 / TTS / ASR 流水账。控制台和 data/logs 都带本地时间。"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Dict, List

from .paths import LOGS_DIR

_lock = threading.Lock()

KIND_CN = {
    "user": "对方",
    "full": "完整回复",
    "spoken": "实际播出",
    "unsaid": "未播出",
    "tts": "TTS",
    "asr": "识别",
    "chat": "对话",
    "note": "系统",
}


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _one_line(text: str) -> str:
    return (text or "").replace("\r", " ").replace("\n", " ").strip()


def _paths():
    day = datetime.now().strftime("%Y-%m-%d")
    return LOGS_DIR / f"talk-{day}.log", LOGS_DIR / f"talk-{day}.jsonl"


def write(kind: str, text: str, **extra: Any) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"t": stamp(), "kind": kind, "text": text or ""}
    rec.update({k: v for k, v in extra.items() if v is not None})
    label = KIND_CN.get(kind, kind)
    shown = _one_line(text)
    if len(shown) > 180:
        shown = shown[:180] + "…"
    line = f"[{rec['t']}] {label}  {shown}"
    print(line, flush=True)
    human, js = _paths()
    payload = json.dumps(rec, ensure_ascii=False)
    with _lock:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with human.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            with js.open("a", encoding="utf-8") as f:
                f.write(payload + "\n")
        except OSError:
            pass
    return rec


def read_today(limit: int = 400) -> List[Dict[str, Any]]:
    _, js = _paths()
    if not js.is_file():
        return []
    try:
        raw = js.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: List[Dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            rec.setdefault("kind", "note")
            rec.setdefault("t", "")
            rec.setdefault("text", "")
            rec["kind_cn"] = KIND_CN.get(str(rec.get("kind")), str(rec.get("kind")))
            rows.append(rec)
    if limit > 0:
        rows = rows[-limit:]
    return rows
