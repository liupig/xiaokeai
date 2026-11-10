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
        ("英雄联盟", "lol", "撸啊撸", "联盟", "league of legends", "リーグ・オブ・レジェンド", "리그 오브 레전드", "롤"),
        "wegame",
        ("leagueclient.exe", "league of legends.exe", "leagueclientux.exe"),
    ),
    Title(("地下城与勇士", "dnf", "던전앤파이터", "던파", "アラド戦記", "dungeon fighter"), "wegame", ("dnf.exe",)),
    Title(("穿越火线", "cf", "crossfire", "크로스파이어"), "wegame", ("crossfire.exe",)),
    Title(("counter-strike 2", "cs2", "cs", "反恐精英", "カウンターストライク", "카운터스트라이크"), "steam", ("cs2.exe",)),
    Title(("dota 2", "dota2", "刀塔", "ドータ", "도타"), "steam", ("dota2.exe",)),
    Title(("elden ring", "艾尔登法环", "エルデンリング", "엘든 링"), "steam", ("eldenring.exe",)),
    Title(("fortnite", "堡垒之夜", "フォートナイト", "포트나이트"), "epic", ("fortniteclient-win64-shipping.exe",)),
    # High-reach PC games (CN names, global names and common short names).
    # The launcher/library still decides whether a title is installed.
    Title(("绝地求生", "pubg", "playerunknown's battlegrounds", "吃鸡"), "steam", ("tslgame.exe",)),
    Title(("apex legends", "apex", "apex英雄", "apex英雄"), "steam", ("r5apex.exe",)),
    Title(("tom clancy's rainbow six siege", "rainbow six siege", "彩虹六号", "彩虹六号围攻", "r6"), "steam", ("rainbowsix.exe",)),
    Title(("grand theft auto v", "gta v", "gta5", "侠盗猎车手5", "侠盗猎车手v"), "steam", ("gta5.exe",)),
    Title(("red dead redemption 2", "荒野大镖客2", "荒野大镖客：救赎2"), "steam", ("rdr2.exe",)),
    Title(("monster hunter world", "怪物猎人世界", "mhw"), "steam", ("monsterhunterworld.exe",)),
    Title(("monster hunter wilds", "怪物猎人：荒野", "怪物猎人荒野"), "steam", ("monsterhunterwilds.exe",)),
    Title(("dark souls iii", "dark souls 3", "黑暗之魂3"), "steam", ("darksoulsiii.exe",)),
    Title(("sekiro", "sekiro: shadows die twice", "只狼", "只狼：影逝二度"), "steam", ("sekiro.exe",)),
    Title(("cyberpunk 2077", "赛博朋克2077", "赛博朋克 2077"), "steam", ("cyberpunk2077.exe",)),
    Title(("baldur's gate 3", "博德之门3", "博德之门 3", "bg3"), "steam", ("bg3.exe",)),
    Title(("the witcher 3", "巫师3", "巫师3：狂猎", "the witcher 3: wild hunt"), "steam", ("witcher3.exe",)),
    Title(("stardew valley", "星露谷物语", "星露谷"), "steam", ("stardew valley.exe",)),
    Title(("terraria", "泰拉瑞亚"), "steam", ("terraria.exe",)),
    Title(("minecraft", "我的世界", "mc"), "steam", ("minecraft.exe",)),
    Title(("rust", "腐蚀"), "steam", ("rustclient.exe",)),
    Title(("dayz", "dayz standalone"), "steam", ("dayz_x64.exe",)),
    Title(("left 4 dead 2", "求生之路2", "求生之路 2", "l4d2"), "steam", ("left4dead2.exe",)),
    Title(("payday 2", "收获日2", "收获日 2"), "steam", ("payday2_win32_release.exe",)),
    Title(("dead by daylight", "黎明杀机", "黎明杀机"), "steam", ("deadbydaylight-win64-shipping.exe",)),
    Title(("palworld", "幻兽帕鲁", "幻兽帕鲁"), "steam", ("palworld-win64-shipping.exe",)),
    Title(("hogwarts legacy", "霍格沃茨之遗", "霍格沃兹之遗"), "steam", ("hogwartslegacy.exe",)),
    Title(("the finals", "THE FINALS", "终极对决"), "steam", ("Discovery.exe",)),
    Title(("helldivers 2", "绝地潜兵2", "绝地潜兵 2"), "steam", ("helldivers2.exe",)),
    Title(("path of exile", "流放之路", "poe"), "steam", ("pathofexile.exe",)),
    Title(("path of exile 2", "流放之路2", "流放之路 2", "poe2"), "steam", ("pathofexile2.exe",)),
    Title(("warframe", "星际战甲"), "steam", ("launcher.exe",)),
    Title(("destiny 2", "命运2", "命运 2"), "steam", ("destiny2.exe",)),
    Title(("deadlock", "死锁"), "steam", ("deadlock.exe",)),
    Title(("team fortress 2", "军团要塞2", "军团要塞 2", "tf2"), "steam", ("hl2.exe",)),
    Title(("garry's mod", "gmod", "盖瑞模组"), "steam", ("gmod.exe",)),
    Title(("civilization vi", "文明6", "文明 6", "文明帝国6"), "steam", ("CivilizationVI.exe",)),
    Title(("total war: three kingdoms", "全面战争：三国", "全面战争三国"), "steam", ("Three_Kingdoms.exe",)),
    Title(("age of empires iv", "帝国时代4", "帝国时代 4"), "steam", ("RelicCardinal.exe",)),
    Title(("rimworld", "环世界"), "steam", ("RimWorldWin64.exe",)),
    Title(("factorio", "异星工厂"), "steam", ("factorio.exe",)),
    Title(("hades", "哈迪斯"), "steam", ("hades.exe",)),
    Title(("hades ii", "哈迪斯2", "哈迪斯 2"), "steam", ("Hades2.exe",)),
    Title(("among us", "amongus", "在我们之中"), "steam", ("Among Us.exe",)),
    Title(("lethal company", "致命公司"), "steam", ("Lethal Company.exe",)),
    Title(("phasmophobia", "恐鬼症"), "steam", ("Phasmophobia.exe",)),
    Title(("subnautica", "深海迷航"), "steam", ("Subnautica.exe",)),
    Title(("the elder scrolls online", "上古卷轴online", "上古卷轴ol", "eso"), "steam", ("eso64.exe",)),
    Title(("starfield", "星空"), "steam", ("Starfield.exe",)),
    Title(("fallout 4", "辐射4", "辐射 4"), "steam", ("Fallout4.exe",)),
    Title(("assassin's creed shadows", "刺客信条：影", "刺客信条影"), "epic", ("ACShadows.exe",)),
    Title(("assassin's creed valhalla", "刺客信条：英灵殿", "刺客信条英灵殿"), "epic", ("ACValhalla.exe",)),
    Title(("rocket league", "火箭联盟"), "epic", ("RocketLeague.exe",)),
    Title(("fall guys", "糖豆人", "糖豆人：终极淘汰赛"), "epic", ("FallGuys_client_game.exe",)),
    Title(("dead island 2", "死亡岛2", "死亡岛 2"), "epic", ("DeadIsland2.exe",)),
    Title(("borderlands 3", "无主之地3", "无主之地 3"), "epic", ("Borderlands3.exe",)),
    Title(("civilization vii", "文明7", "文明 7", "文明帝国7"), "steam", ("CivilizationVII.exe",)),
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
