"""一台机器上的一个已安装游戏，或一次「只开平台」。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Game:
    platform: str
    name: str
    key: str = ""
    install_dir: str = ""
    installed: bool = False
    processes: tuple[str, ...] = ()
    launcher_argv: tuple[str, ...] = ()
    game_argv: tuple[str, ...] = ()
