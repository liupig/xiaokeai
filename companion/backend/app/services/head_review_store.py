import json
from datetime import datetime, timezone
from typing import Any

from ..paths import DATA_DIR

FILE_PATH = DATA_DIR / "head_auto_review.json"


def save_motion(body: dict[str, Any]):
    name = str(body.get("name") or "").strip()
    if not name:
        raise ValueError("动作名称不能为空")
    raw_samples = body.get("samples")
    if not isinstance(raw_samples, list):
        raise ValueError("samples 必须是数组")
    samples = {}
    for item in raw_samples:
        if not isinstance(item, dict):
            continue
        combo_id = str(item.get("combo_id") or "")
        verdict = str(item.get("verdict") or "")
        if not combo_id or verdict not in ("ok", "bad"):
            continue
        samples[combo_id] = {
            "ratio": max(0.0, min(1.0, float(item.get("ratio") or 0))),
            "verdict": verdict,
        }
    data = {"version": 1, "updated_at": "", "motions": {}}
    if FILE_PATH.is_file():
        try:
            data = json.loads(FILE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    now = datetime.now(timezone.utc).isoformat()
    motions = data.setdefault("motions", {})
    motions[name] = {
        "label": str(body.get("label") or name),
        "updated_at": now,
        "samples": samples,
    }
    data["version"] = 1
    data["updated_at"] = now
    FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(FILE_PATH)
    return {"ok": True, "path": str(FILE_PATH), "name": name, "count": len(samples)}
