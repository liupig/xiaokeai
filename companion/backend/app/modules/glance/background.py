"""电影和音乐只补非剧情背景。可能剧透的句子不进现场。"""
from __future__ import annotations

import os
import threading

_SPOILER = ("剧情", "结局", "最后", "反转", "谁死", "杀死", "歌词全文", "剧透", "后来", "原来他", "大结局")


def keep_background(lines: list[str]) -> list[str]:
    kept: list[str] = []
    for line in lines:
        text = " ".join((line or "").split())
        if len(text) < 2 or any(word in text for word in _SPOILER):
            continue
        kept.append(text[:80])
        if len(kept) >= 3:
            break
    return kept


def schedule(scene: str, title: str, artist: str, apply) -> None:
    if os.environ.get("XIAOKE_GLANCE_LOOKUP", "1") == "0":
        apply([])
        return

    def run() -> None:
        try:
            apply(keep_background(_titles(scene, title, artist)))
        except Exception:
            apply([])

    threading.Thread(target=run, name="glance-background", daemon=True).start()


def _titles(scene: str, title: str, artist: str) -> list[str]:
    from ..websearch.service import _search

    query = f"{title} {artist} 类型 主演 歌手".strip()
    merged, _cards, _names = _search(query)
    return [item for item, _url in merged[:5]]
