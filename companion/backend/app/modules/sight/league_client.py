"""Optional read-only local LoL telemetry. No account credentials or game control."""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_checked = 0.0
_cached: dict = {}


def parse_state(data: dict) -> dict:
    active = data.get("activePlayer") or {}
    name = active.get("summonerName")
    riot_id = active.get("riotId")
    players = data.get("allPlayers") or []
    own = next((p for p in players if (name and p.get("summonerName") == name)
                or (riot_id and p.get("riotId") == riot_id)), None)
    if not own or not own.get("championName"):
        return {}
    return {
        "hero": str(own["championName"]),
        "dead": bool(own.get("isDead")),
        "respawn": float(own.get("respawnTimer") or 0),
        "game_time": float((data.get("gameData") or {}).get("gameTime") or 0),
        "scores": dict(own.get("scores") or {}),
        "source": "liveclient",
    }


def latest() -> dict:
    """Bounded cached probe; unavailability must never block visual companionship."""
    global _checked, _cached
    with _lock:
        if time.monotonic() - _checked < 3:
            return dict(_cached)
        _checked = time.monotonic()
        try:
            import httpx

            # The game's localhost API uses its own certificate. Never send this
            # request to a configurable external URL, and never use proxy env vars.
            with httpx.Client(verify=False, trust_env=False, timeout=0.3) as client:
                response = client.get("https://127.0.0.1:2999/liveclientdata/allgamedata")
                response.raise_for_status()
                _cached = parse_state(response.json())
        except Exception:
            _cached = {}
        return dict(_cached)
