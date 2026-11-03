"""三个启动器。库和启动地址都从本机读，不写死盘符。"""
from __future__ import annotations

from . import epic, steam, wegame
from .model import Game

LABELS = {"wegame": "WeGame", "steam": "Steam", "epic": "Epic"}
_MODS = {"wegame": wegame, "steam": steam, "epic": epic}


def launcher(platform: str, host) -> str:
    mod = _MODS.get(platform)
    if mod is None:
        return ""
    return mod.launcher(host)


def library(platform: str, host) -> list[Game]:
    mod = _MODS.get(platform)
    if mod is None:
        return []
    try:
        return mod.library(host)
    except OSError as exc:
        print(f"[play] {platform} library failed: {exc}")
        return []
