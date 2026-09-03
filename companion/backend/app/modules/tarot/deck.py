"""78 张牌库。发牌机只认这里的 id，不让模型抽牌。"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...paths import ASSETS_DIR

TAROT_DIR = ASSETS_DIR / "tarot"

Card = Dict[str, object]

_MAJORS: List[Tuple[str, str, str, str]] = [
    ("00-fool", "愚者", "抬脚要走，新的一截还没地图", "没看脚下，把冒险当成逃"),
    ("01-magician", "魔术师", "手里有家伙，事情开得动", "光说不练，把姿态当本事"),
    ("02-priestess", "女祭司", "先别说破，里面还有没翻开的一层", "自己也没想清，却装成看透了"),
    ("03-empress", "皇后", "被好好养着，东西能长出来", "惯得发懒，丰盛变成负担"),
    ("04-emperor", "皇帝", "得有人拍板，秩序能撑住场", "管太死，把人管成棋子"),
    ("05-hierophant", "教皇", "老规矩还在，有师承也有依靠", "被规矩绑住，不敢用自己的判断"),
    ("06-lovers", "恋人", "得选一边，心和身要对齐", "心里两头扯，承诺说了又含糊"),
    ("07-chariot", "战车", "咬牙往前，意志把方向拽住", "方向拧着，两股劲互相耗"),
    ("08-strength", "力量", "柔的更能按住，不是硬顶", "硬撑着，把牙关当勇气"),
    ("09-hermit", "隐者", "先自己把灯打开，问自己比问别人准", "躲太深，把独处过成隔绝"),
    ("10-wheel", "命运之轮", "这轮在转，时机比力气大", "别死抓紧过气的，转过去的捞不回来"),
    ("11-justice", "正义", "把账算明白，公平先对自己", "偏心了自己却不认，账是歪的"),
    ("12-hanged", "倒吊人", "先停一下，换个角度看才走得动", "耗着不肯动，把等待过成麻木"),
    ("13-death", "死神", "旧的该放下，腾地方给下一截", "死死抓着不放，结束被拖着走"),
    ("14-temperance", "节制", "兑一兑别走极端，两样东西能共处", "调和过度没味道，谁都不得罪也谁都不真"),
    ("15-devil", "恶魔", "锁其实松着，瘾和绑是自己套的", "自己套上去的，还把锁当项链"),
    ("16-tower", "塔", "该拆的会拆，假稳当撑不住", "假装没裂，裂缝上继续盖楼"),
    ("17-star", "星星", "还有一口气，远一点的光也够走", "盼太远，把希望过成空等"),
    ("18-moon", "月亮", "别被影吓到，看不清不等于有鬼", "自己吓自己，把想象喂得太大"),
    ("19-sun", "太阳", "这会儿亮堂，被看见也不用缩", "亮得刺眼，快活过成就晒"),
    ("20-judgement", "审判", "该起来了，旧账翻开是为了走", "还躺着装没听见，叫号叫到了也不起"),
    ("21-world", "世界", "这圈走完了，可以完整地收住", "差临门一脚，完整就差自己点头"),
]

_SUITS = {
    "wands": ("竹杖", "wands"),
    "cups": ("瓷盏", "cups"),
    "swords": ("古剑", "swords"),
    "coins": ("玉币", "coins"),
}

_PIPS: List[Tuple[str, str, str]] = [
    ("01", "一", "开了个头，劲刚起来"),
    ("02", "二", "两边看着，还没落一边"),
    ("03", "三", "开始成形，有了小气候"),
    ("04", "四", "先把摊子稳住，有处可歇"),
    ("05", "五", "拧着、耗着，有点不服气"),
    ("06", "六", "缓过一口气，有人伸手或自己松了"),
    ("07", "七", "还在掂量，想得多、落地少"),
    ("08", "八", "得动手了，不能再只想"),
    ("09", "九", "快到了，也更沉、更熬"),
    ("10", "十", "这一段落了，该卸货或收场"),
]

_COURTS: List[Tuple[str, str, str]] = [
    ("page", "侍从", "刚上手"),
    ("knight", "骑士", "已经在跑"),
    ("queen", "王后", "心里有数"),
    ("king", "国王", "得扛事"),
]

_PIP_HINT_REV = {
    "01": "火候还没起，站在门口没迈出去",
    "02": "拖着不选，两边都想要",
    "03": "刚聚上的又散了",
    "04": "稳成了窝，守着不肯动",
    "05": "别只盯输的那头，气还堵着",
    "06": "旧的温存泡太久，该往前走",
    "07": "想太多没落地，机会在眼前也犹豫",
    "08": "困在里头，手脚被自己绑住",
    "09": "担心压过来了，快到却更怕",
    "10": "包袱太沉，这一摊收不了场",
}

_COURT_HINT_REV = {
    "page": "消息没听全，或把新鲜劲当成本事",
    "knight": "冲太猛，方向还没看清",
    "queen": "情绪淹了，感受压过判断",
    "king": "端着不松，扛着面子不卸肩",
}

_SUIT_THEME = {
    "wands": ("行动、热情、想做的事和那股劲", "火候过了、熄了，或把摊子守成了窝"),
    "cups": ("心情、关系、心里那摊水", "情漫出来、干了，或沉在旧水里"),
    "swords": ("念头、口舌、要不要把事切开", "想太多、话太伤，或把自己切累了"),
    "coins": ("手头、身子、过日子的实处", "抓太紧、空了，或把安全感攥成抠"),
}


def _card(
    cid: str,
    name: str,
    rel: str,
    *,
    arcana: str,
    suit: str,
    hint_up: str,
    hint_rev: str,
) -> Card:
    return {
        "id": cid,
        "name": name,
        "file": rel.replace("\\", "/"),
        "arcana": arcana,
        "suit": suit,
        "hint_up": hint_up,
        "hint_rev": hint_rev,
    }


def all_cards() -> List[Card]:
    out: List[Card] = []
    for fid, name, up, rev in _MAJORS:
        num = fid.split("-", 1)[0]
        cid = f"major/{fid}"
        out.append(_card(
            cid, name, f"major/{fid}.png",
            arcana="major", suit="", hint_up=up, hint_rev=rev,
        ))
        out[-1]["index"] = int(num)
    for suit, (suit_name, folder) in _SUITS.items():
        for fid, pip_name, up in _PIPS:
            cid = f"{suit}/{fid}"
            out.append(_card(
                cid, f"{suit_name}{pip_name}", f"{folder}/{fid}.png",
                arcana="minor", suit=suit,
                hint_up=up, hint_rev=_PIP_HINT_REV[fid],
            ))
        for fid, court_name, up in _COURTS:
            cid = f"{suit}/{fid}"
            out.append(_card(
                cid, f"{suit_name}{court_name}", f"{folder}/{fid}.png",
                arcana="minor", suit=suit,
                hint_up=up, hint_rev=_COURT_HINT_REV[fid],
            ))
    return out


_CARDS: List[Card] = all_cards()
_BY_ID: Dict[str, Card] = {str(c["id"]): c for c in _CARDS}


def get(card_id: str) -> Optional[Card]:
    return _BY_ID.get(card_id)


def list_cards() -> List[Card]:
    return list(_CARDS)


def art_path(rel: str) -> Path:
    return TAROT_DIR / rel.replace("\\", "/")


def has_art(rel: str) -> bool:
    p = art_path(rel)
    return p.is_file() and p.stat().st_size > 32


def back_exists() -> bool:
    return has_art("back.png")


def angle_for(card: Card, reversed: bool) -> str:
    """给 overlay 用的解读底，不是让她照着念的百科。"""
    if str(card.get("arcana") or "") == "major":
        return str(card.get("hint_rev") if reversed else card.get("hint_up") or "")
    suit = str(card.get("suit") or "")
    theme_up, theme_rev = _SUIT_THEME.get(suit, ("这件事的实处", "这件事拧着"))
    pip = str(card.get("hint_rev") if reversed else card.get("hint_up") or "")
    theme = theme_rev if reversed else theme_up
    if pip:
        return f"{theme}；这一张偏「{pip}」"
    return theme


def enrich(card: Card) -> Card:
    rel = str(card.get("file") or "")
    item = dict(card)
    item["has_art"] = has_art(rel)
    item["url"] = f"/assets/tarot/{rel}" if rel else ""
    item["back_url"] = "/assets/tarot/back.png"
    item["back_ready"] = back_exists()
    return item
