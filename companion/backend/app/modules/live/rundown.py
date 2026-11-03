"""节目单。聊天、读评论、跳舞、猜数字、许愿循环。没授权的歌和舞跳过。"""
from __future__ import annotations

from .config import feature_on, song_titles

_BASE = (
    ("chat", 180),
    ("read", 70),
    ("dance", 90),
    ("game", 90),
    ("wish", 70),
    ("chat", 180),
)


def segments(cfg: dict) -> list[tuple[str, int]]:
    licensed = bool((cfg.get("compliance") or {}).get("bgm_licensed"))
    ritual = feature_on(cfg, "ritual")
    out: list[tuple[str, int]] = []
    for sid, sec in _BASE:
        if sid == "dance" and not licensed:
            continue
        if sid == "wish" and not ritual:
            continue
        out.append((sid, sec))
        if sid == "dance" and song_titles(cfg):
            out.append(("song", 60))
    return out or [("chat", 180)]


class Rundown:
    def __init__(self) -> None:
        self.started = 0.0

    def start(self, now: float) -> None:
        self.started = now

    def current(self, now: float, cfg: dict) -> dict:
        if not feature_on(cfg, "rundown"):
            return {"id": "chat", "index": 0, "left": 0}
        segs = segments(cfg)
        total = sum(sec for _sid, sec in segs) or 1
        elapsed = max(0.0, now - self.started) % total
        cursor = 0.0
        for index, (sid, sec) in enumerate(segs):
            if elapsed < cursor + sec:
                return {"id": sid, "index": index, "left": int(cursor + sec - elapsed)}
            cursor += sec
        sid, sec = segs[0]
        return {"id": sid, "index": 0, "left": sec}
