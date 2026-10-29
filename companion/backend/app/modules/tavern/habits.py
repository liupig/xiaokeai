"""每个座位的打牌习性。按角色记在本机，打得越久越清楚。"""
import json

from ...paths import DATA_DIR

_PATH = DATA_DIR / "tavern-habits.json"
_NAMES = {"you": "KE", "qin": "XiaO", "bar": "AI"}


def _blank() -> dict:
    return {"plays": 0, "follows": 0, "opens": 0, "calls": 0, "call_hit": 0, "call_miss": 0, "bluffs": 0, "truths": 0}


def _read() -> dict:
    if not _PATH.exists():
        return {}
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def note_into(seats: dict, note: dict) -> None:
    """把一手记进习性。同一份 seats 可以被反复调用。"""
    kind = str(note.get("t") or "")
    if kind == "play":
        who = str(note.get("who") or "")
        if not who:
            return
        row = seats.setdefault(who, _blank())
        row["plays"] = int(row.get("plays") or 0) + 1
        if note.get("follow"):
            row["follows"] = int(row.get("follows") or 0) + 1
        else:
            row["opens"] = int(row.get("opens") or 0) + 1
        return
    if kind != "reveal":
        return
    caller = str(note.get("caller") or "")
    actor = str(note.get("actor") or "")
    if caller:
        row = seats.setdefault(caller, _blank())
        row["calls"] = int(row.get("calls") or 0) + 1
        key = "call_miss" if note.get("honest") else "call_hit"
        row[key] = int(row.get(key) or 0) + 1
    if actor:
        row = seats.setdefault(actor, _blank())
        key = "truths" if note.get("honest") else "bluffs"
        row[key] = int(row.get(key) or 0) + 1


def suspicion(seats: dict) -> dict[str, float]:
    """正数表示这个人爱诈，揭穿更值得。负数表示出牌比较老实。"""
    out: dict[str, float] = {}
    for pid, row in seats.items():
        if not isinstance(row, dict):
            continue
        shown = int(row.get("bluffs") or 0) + int(row.get("truths") or 0)
        if shown < 3:
            continue
        rate = int(row.get("bluffs") or 0) / shown
        out[str(pid)] = round((rate - 0.35) * 0.55, 3)
    return out


def describe(seats: dict, her_name: str = "") -> str:
    names = {**_NAMES, "her": her_name or "她"}
    lines: list[str] = []
    for pid in ("you", "qin", "bar", "her"):
        row = seats.get(pid)
        if not isinstance(row, dict):
            continue
        plays = int(row.get("plays") or 0)
        calls = int(row.get("calls") or 0)
        bluffs = int(row.get("bluffs") or 0)
        truths = int(row.get("truths") or 0)
        shown = bluffs + truths
        if plays + calls + shown == 0:
            continue
        if shown >= 3 and bluffs / shown >= 0.45:
            habit = "爱诈"
        elif shown >= 3 and bluffs / shown <= 0.2:
            habit = "出牌比较老实"
        elif shown:
            habit = "有时诈，有时老实"
        else:
            habit = "还没被揭开过"
        hits = int(row.get("call_hit") or 0)
        if calls >= 3 and hits / calls >= 0.55:
            eye = "揭穿比较准"
        elif calls >= 3 and hits / calls <= 0.3:
            eye = "揭穿经常落空"
        elif calls == 0 and plays >= 3:
            eye = "很少揭穿，多半选择跟"
        elif calls:
            eye = f"揭穿过{calls}次"
        else:
            eye = "还没怎么揭穿"
        name = names.get(pid, pid)
        lines.append(f"{name}：出过{plays}手。被揭开{shown}次，其中撒谎{bluffs}次，{habit}。{eye}。")
    if not lines:
        return "习性还没记下。打得越久，这里越清楚。"
    return "你记得的习性：\n" + "\n".join(lines)


def observe(character_id: int, night: int, note: dict) -> None:
    seq = int(note.get("seq") or 0)
    if seq <= 0 or not character_id:
        return
    data = _read()
    key = str(character_id)
    row = data.get(key) if isinstance(data.get(key), dict) else {}
    seats = row.get("seats") if isinstance(row.get("seats"), dict) else {}
    if int(row.get("night") or 0) != int(night):
        row["night"] = int(night)
        row["seen"] = 0
    if seq <= int(row.get("seen") or 0):
        return
    note_into(seats, note)
    row["seen"] = seq
    row["seats"] = seats
    data[key] = row
    _write(data)


def load_seats(character_id: int) -> dict:
    data = _read()
    row = data.get(str(character_id)) if character_id else None
    if not isinstance(row, dict):
        return {}
    seats = row.get("seats")
    return seats if isinstance(seats, dict) else {}


def lines(character_id: int, her_name: str = "") -> str:
    return describe(load_seats(character_id), her_name)


def bias(character_id: int) -> dict[str, float]:
    return suspicion(load_seats(character_id))
