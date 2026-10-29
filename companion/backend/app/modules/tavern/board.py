"""四人战绩。按角色记在本机，关了酒馆也还在。"""
import json

from ...paths import DATA_DIR

_PATH = DATA_DIR / "tavern-board.json"


def _read() -> dict:
    if not _PATH.exists():
        return {}
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load(character_id: int) -> dict:
    row = _read().get(str(character_id)) or {}
    return row if isinstance(row, dict) else {}


def apply(character_id: int, places: list[dict]) -> dict:
    data = _read()
    key = str(character_id)
    row = data.get(key) if isinstance(data.get(key), dict) else {}
    for place in places:
        pid = str(place.get("id") or "")
        if not pid:
            continue
        cur = row.get(pid) if isinstance(row.get(pid), dict) else {}
        cur = {
            "played": int(cur.get("played") or 0) + 1,
            "wins": int(cur.get("wins") or 0) + (1 if str(place.get("tag") or "") in ("win", "finish") else 0),
            "points": int(cur.get("points") or 0) + int(place.get("points") or 0),
        }
        row[pid] = cur
    data[key] = row
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return row
