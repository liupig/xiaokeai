"""Durable diagnostics for live-video testing.

We retain metadata and model text, never raw screen frames or a recording.
"""
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import threading

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
_session = datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_PATH = LOG_DIR / f"live-video-{_session}.jsonl"
RAW_DIR = LOG_DIR / f"live-video-{_session}-raw"
MODEL_DIR = LOG_DIR / f"live-video-{_session}-model-input"
_rows = deque(maxlen=2_000)
_lock = threading.Lock()


def _json_default(value):
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def record(*, event="inference", text="", prompt="", suppressed=False,
           stats=None, elapsed_ms=0, reason="", **extra):
    """Append one diagnostic event and keep it immediately queryable."""
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "text": text,
        "prompt": prompt,
        "suppressed": bool(suppressed),
        "elapsed_ms": elapsed_ms,
        "reason": reason,
        **(stats or {}),
        **extra,
    }
    with _lock:
        _rows.append(row)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=_json_default) + "\n")
            handle.flush()
    return row


def recent(limit=100):
    with _lock:
        return list(_rows)[-max(1, min(int(limit), 2_000)):]


def _stamp(captured_total: int, suffix: str = ""):
    return f"{datetime.now().strftime('%H%M%S-%f')}-{captured_total:08d}{suffix}"


def save_raw_frame(image, *, captured_total=0):
    """Save the full-resolution screen frame before masking/downscaling, losslessly."""
    RAW_DIR.mkdir(exist_ok=True)
    path = RAW_DIR / f"{_stamp(captured_total)}.png"
    image.convert("RGB").save(path, format="PNG", compress_level=3)
    return str(path)


def save_model_frames(images, *, frame_ids):
    """Losslessly persist the exact PIL frames handed to MiniCPM for one inference."""
    if not images:
        return []
    batch_dir = MODEL_DIR / _stamp(int(frame_ids[-1]))
    batch_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, (image, frame_id) in enumerate(zip(images, frame_ids), start=1):
        path = batch_dir / f"{index:02d}-capture-{frame_id:08d}.png"
        image.convert("RGB").save(path, format="PNG", compress_level=3)
        paths.append(str(path))
    return paths


def info():
    with _lock:
        count = len(_rows)
    return {
        "path": str(LOG_PATH),
        "raw_frame_dir": str(RAW_DIR),
        "model_input_dir": str(MODEL_DIR),
        "session": _session,
        "in_memory": count,
        "policy": "测试期无损保存连续原始屏幕帧、每次送入模型的帧序列、元数据和文本；不编码成视频文件",
    }
