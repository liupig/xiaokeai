"""直播配置。开关缺省打开，彩排缺省关闭。总开关在 modules.live，默认关。"""
from __future__ import annotations

from typing import Any

FEATURE_KEYS = (
    "bilibili",
    "douyin",
    "scheduler",
    "reply",
    "gifts",
    "audience",
    "rundown",
    "idle",
    "budget",
    "watchdog",
    "ai_label",
    "content_gate",
    "ritual",
    "rehearsal",
    "commands",
    "interrupt",
)

_FEATURE_DEFAULT_OFF = frozenset({"rehearsal"})


def default_live() -> dict[str, Any]:
    return {
        "douyin": {"room": "", "push_secret": "", "room_id": ""},
        "bilibili": {
            "access_key_id": "",
            "access_key_secret": "",
            "app_id": 0,
            "code": "",
        },
        "features": {key: key not in _FEATURE_DEFAULT_OFF for key in FEATURE_KEYS},
        "compliance": {
            "strict": True,
            "ack_voice": False,
            "ack_model": False,
            "ack_bgm": False,
            "bgm_licensed": False,
        },
        "budget": {
            "cap_cny": 30,
            "cny_per_1k": 0.004,
            "fallback_base_url": "",
            "fallback_model": "",
            "fallback_api_key": "",
        },
        "pace": {
            "batch_sec": 20,
            "user_cooldown_sec": 8,
            "batch_size": 6,
            "idle_sec": 45,
            "session_max_min": 0,
            "quiet_min": 0,
        },
        "persona": {"catchphrase": "我在呢", "style": ""},
        "schedule": {"note": "", "community": ""},
        "songs": "",
        "block_words": "",
    }


def feature_on(cfg: dict, name: str) -> bool:
    feats = cfg.get("features") if isinstance(cfg, dict) else None
    if not isinstance(feats, dict) or name not in feats:
        return name not in _FEATURE_DEFAULT_OFF
    return bool(feats.get(name))


def missing_acks(cfg: dict) -> list[str]:
    """严格模式下，没确认的授权项。空列表才能开播。"""
    comp = cfg.get("compliance") if isinstance(cfg, dict) else None
    if not isinstance(comp, dict) or not bool(comp.get("strict", True)):
        return []
    missing = []
    if not comp.get("ack_voice"):
        missing.append("voice")
    if not comp.get("ack_model"):
        missing.append("model")
    if not comp.get("ack_bgm"):
        missing.append("bgm")
    return missing


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = default
    if num < low:
        return low
    if num > high:
        return high
    return num


def normalize(raw: Any) -> dict[str, Any]:
    base = default_live()
    src = raw if isinstance(raw, dict) else {}
    for key, val in src.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            merged = dict(base[key])
            merged.update(val)
            base[key] = merged
        elif key in base or key in ("songs", "block_words"):
            base[key] = val
    feats = dict(base["features"])
    incoming = src.get("features") if isinstance(src.get("features"), dict) else {}
    for key in FEATURE_KEYS:
        if key in incoming:
            feats[key] = bool(incoming[key])
        else:
            feats[key] = key not in _FEATURE_DEFAULT_OFF
    base["features"] = feats
    comp = base["compliance"]
    for key in ("strict", "ack_voice", "ack_model", "ack_bgm", "bgm_licensed"):
        comp[key] = bool(comp.get(key))
    pace = base["pace"]
    pace["batch_sec"] = int(_clamp(pace.get("batch_sec"), 5, 120, 20))
    pace["user_cooldown_sec"] = int(_clamp(pace.get("user_cooldown_sec"), 1, 120, 8))
    pace["batch_size"] = int(_clamp(pace.get("batch_size"), 1, 12, 6))
    pace["idle_sec"] = int(_clamp(pace.get("idle_sec"), 15, 600, 45))
    pace["session_max_min"] = int(_clamp(pace.get("session_max_min"), 0, 720, 0))
    pace["quiet_min"] = int(_clamp(pace.get("quiet_min"), 0, 180, 0))
    budget = base["budget"]
    budget["cap_cny"] = _clamp(budget.get("cap_cny"), 0, 100000, 30)
    budget["cny_per_1k"] = _clamp(budget.get("cny_per_1k"), 0, 100, 0.004)
    for key in ("fallback_base_url", "fallback_model", "fallback_api_key"):
        budget[key] = str(budget.get(key) or "").strip()
    bili = base["bilibili"]
    bili["access_key_id"] = str(bili.get("access_key_id") or "").strip()
    bili["access_key_secret"] = str(bili.get("access_key_secret") or "").strip()
    bili["code"] = str(bili.get("code") or "").strip()
    try:
        bili["app_id"] = int(bili.get("app_id") or 0)
    except (TypeError, ValueError):
        bili["app_id"] = 0
    douyin = base["douyin"]
    douyin["room"] = str(douyin.get("room") or "")
    douyin["push_secret"] = str(douyin.get("push_secret") or "")
    douyin["room_id"] = str(douyin.get("room_id") or "").strip()
    persona = base["persona"]
    persona["catchphrase"] = str(persona.get("catchphrase") or "我在呢").strip()[:24] or "我在呢"
    persona["style"] = str(persona.get("style") or "").strip()[:200]
    sched = base["schedule"]
    sched["note"] = str(sched.get("note") or "").strip()[:80]
    sched["community"] = str(sched.get("community") or "").strip()[:200]
    base["songs"] = str(base.get("songs") or "").strip()[:2000]
    base["block_words"] = str(base.get("block_words") or "").strip()[:2000]
    return base


def merge_live(current: Any, patch: Any) -> dict[str, Any]:
    base = normalize(current)
    src = patch if isinstance(patch, dict) else {}
    for key, val in src.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            nxt = dict(base[key])
            nxt.update(val)
            base[key] = nxt
        else:
            base[key] = val
    return normalize(base)


def batch_window(cfg: dict) -> int:
    if not feature_on(cfg, "scheduler"):
        return 0
    return int(cfg["pace"]["batch_sec"])


def user_cooldown(cfg: dict) -> int:
    if not feature_on(cfg, "scheduler"):
        return 0
    return int(cfg["pace"]["user_cooldown_sec"])


def song_titles(cfg: dict) -> list[str]:
    if not (cfg.get("compliance") or {}).get("bgm_licensed"):
        return []
    out = []
    for line in str(cfg.get("songs") or "").splitlines():
        title = line.strip().strip("《》")
        if title and title not in out:
            out.append(title[:40])
    return out[:40]
