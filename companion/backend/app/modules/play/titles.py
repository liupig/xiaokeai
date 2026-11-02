"""口头名字和安装库里的名字怎么对上。

WeGame、Steam、Epic 只在这里登记「这个名字归哪个平台」。
库里扫到的游戏不必出现在这张表里，表只负责别名和默认平台。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


def norm(text: str) -> str:
    raw = (text or "").lower().strip().replace("’", "'")
    return re.sub(r"[\s_\-·:：'\"“”]+", "", raw)


@dataclass(frozen=True)
class Title:
    names: tuple[str, ...]
    home: str
    processes: tuple[str, ...] = ()


# 只登记口头别名。安装目录、启动器 exe、游戏号都从这台电脑现读。
TITLES: tuple[Title, ...] = (
    Title(
        ("英雄联盟", "lol", "league of legends", "リーグ・オブ・レジェンド", "리그 오브 레전드", "롤"),
        "wegame",
        ("leagueclient.exe", "league of legends.exe", "leagueclientux.exe"),
    ),
    Title(("地下城与勇士", "dnf", "던전앤파이터", "던파", "アラド戦記", "dungeon fighter"), "wegame", ("dnf.exe",)),
    Title(("穿越火线", "cf", "crossfire", "크로스파이어"), "wegame", ("crossfire.exe",)),
    Title(("counter-strike 2", "cs2", "cs", "反恐精英", "カウンターストライク", "카운터스트라이크"), "steam", ("cs2.exe",)),
    Title(("dota 2", "dota2", "刀塔", "ドータ", "도타"), "steam", ("dota2.exe",)),
    Title(("elden ring", "艾尔登法环", "エルデンリング", "엘든 링"), "steam", ("eldenring.exe",)),
    Title(("fortnite", "堡垒之夜", "フォートナイト", "포트나이트"), "epic", ("fortniteclient-win64-shipping.exe",)),
)


_BY_NORM: dict[str, Title] = {}
for _title in TITLES:
    for _name in _title.names:
        _BY_NORM[norm(_name)] = _title


_PLATFORM_NAMES = {
    "wegame": "wegame",
    "steam": "steam",
    "epic": "epic",
    "epicgames": "epic",
}


def title_of(name: str) -> Title | None:
    return _BY_NORM.get(norm(name))


def names_match(query: str, game_name: str) -> bool:
    left = norm(query)
    right = norm(game_name)
    if not left or not right:
        return False
    if left == right:
        return True
    a = title_of(query)
    b = title_of(game_name)
    return bool(a and b and a is b)


def platform_name(query: str) -> str:
    return _PLATFORM_NAMES.get(norm(query), "")


def prefer(region: str) -> tuple[str, ...]:
    if (region or "").lower() == "intl":
        return ("steam", "epic", "wegame")
    return ("wegame", "steam", "epic")
