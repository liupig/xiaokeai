"""78 张牌库。发牌机只认这里的 id，不让模型抽牌。"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...paths import ASSETS_DIR, LOCAL_ASSETS_DIR, resolve_asset_file
from . import lore

TAROT_DIR = LOCAL_ASSETS_DIR / "tarot"
if not TAROT_DIR.is_dir():
    TAROT_DIR = ASSETS_DIR / "tarot"

Card = Dict[str, object]

_MAJORS: List[Tuple[str, str, str, str]] = [
    ("00-fool", "愚者", "抬脚要走，新的一截还没地图", "脚步有点急，先看一眼脚下再迈"),
    ("01-magician", "魔术师", "手里有家伙，事情开得动", "家伙还在，做比说更开得动"),
    ("02-priestess", "女祭司", "先别说破，里面还有没翻开的一层", "心里那层还没亮，不必装成已经看透"),
    ("03-empress", "皇后", "被好好养着，东西能长出来", "丰盛有点沉，给自己留一点空就好"),
    ("04-emperor", "皇帝", "得有人拍板，秩序能撑住场", "管得有点满，松一寸场子反而稳"),
    ("05-hierophant", "教皇", "老规矩还在，有师承也有依靠", "规矩还在，也可以用自己的判断走一步"),
    ("06-lovers", "恋人", "得选一边，心和身要对齐", "两头都在扯，先认心里偏向哪边"),
    ("07-chariot", "战车", "咬牙往前，意志把方向拽住", "两股劲拧着，先把方向认清再加油"),
    ("08-strength", "力量", "柔的更能按住，不是硬顶", "牙关咬太紧了，柔一点反而按得住"),
    ("09-hermit", "隐者", "先自己把灯打开，问自己比问别人准", "灯还在自己手里，出来透口气也不算走远"),
    ("10-wheel", "命运之轮", "这轮在转，时机比力气大", "过气的先松手，下一格才转得进来"),
    ("11-justice", "正义", "把账算明白，公平先对自己", "账还没算平，对自己诚实一点就松了"),
    ("12-hanged", "倒吊人", "先停一下，换个角度看才走得动", "停得有点久了，换个角度就能迈一步"),
    ("13-death", "死神", "旧的该放下，腾地方给下一截", "旧的还攥着，松一点才腾得出下一截"),
    ("14-temperance", "节制", "兑一兑别走极端，两样东西能共处", "兑得太淡了，留一点自己的味道也行"),
    ("15-devil", "恶魔", "锁其实松着，瘾和绑是自己套的", "锁看着紧，钥匙其实在自己这边"),
    ("16-tower", "塔", "该拆的会拆，假稳当撑不住", "裂痕已经看见了，停一停比再盖一层稳"),
    ("17-star", "星星", "还有一口气，远一点的光也够走", "光还在，不必盼到很远才肯迈步"),
    ("18-moon", "月亮", "别被影吓到，看不清不等于有鬼", "影有点大，看清一小块就够今晚"),
    ("19-sun", "太阳", "这会儿亮堂，被看见也不用缩", "亮得有点晃，收一点光也还是暖的"),
    ("20-judgement", "审判", "该起来了，旧账翻开是为了走", "叫号听到了，掀一角就行，不必一次起身"),
    ("21-world", "世界", "这圈走完了，可以完整地收住", "就差自己点一下头，完整已经在门口了"),
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
    "01": "火候还在门口，迈一小步就开了",
    "02": "两边都想要，先认心里偏向哪边",
    "03": "刚聚上的散了一点，还可以再拢回来",
    "04": "稳成了窝，留一扇窗就透气了",
    "05": "气还堵着，别只盯输的那头",
    "06": "旧的温存泡久了，往前走一步也不算忘",
    "07": "想得多，落地一小步就够",
    "08": "手脚有点绑，解开一根就能动",
    "09": "担心压过来了，快到的时候慢一点也行",
    "10": "包袱有点沉，卸一件就轻了",
}

_COURT_HINT_REV = {
    "page": "消息还没听全，新鲜劲先收一收",
    "knight": "跑得有点猛，看清方向再加速",
    "queen": "感受有点满，留一点给判断",
    "king": "肩上扛着，卸一点也不掉份",
}

_SUIT_THEME = {
    "wands": ("行动、热情、想做的事和那股劲", "火候过了或熄了，透口气再点火"),
    "cups": ("心情、关系、心里那摊水", "情漫出来或沉在旧水里，舀一口就够今晚"),
    "swords": ("念头、口舌、要不要把事切开", "想太多、话太利，先把刀放下再说"),
    "coins": ("手头、身子、过日子的实处", "抓太紧或空了，松一寸才握得住"),
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
    rel = (rel or "").replace("\\", "/").lstrip("/")
    found = resolve_asset_file(f"tarot/{rel}")
    if found is not None:
        return found
    return TAROT_DIR / rel


def has_art(rel: str) -> bool:
    p = art_path(rel)
    return p.is_file() and p.stat().st_size > 32


def back_exists() -> bool:
    return has_art("back.png")


def angle_for(card: Card, reversed: bool, lang: str | None = None) -> str:
    """给 overlay 用的解读底。中文走牌面文学稿；其它语言只用该语言的牌名，不把玉币竹杖送进提示。"""
    from ...locale_pack import current_reply, normalize
    lang = normalize(lang or current_reply())
    if lang == "zh-CN":
        cid = str(card.get("id") or "")
        text = lore.angle(cid, reversed)
        if text:
            return text
        if str(card.get("arcana") or "") == "major":
            return str(card.get("hint_rev") if reversed else card.get("hint_up") or "")
        suit = str(card.get("suit") or "")
        theme_up, theme_rev = _SUIT_THEME.get(suit, ("这件事的实处", "这件事拧着"))
        pip = str(card.get("hint_rev") if reversed else card.get("hint_up") or "")
        theme = theme_rev if reversed else theme_up
        if pip:
            return f"{theme}；这一张偏「{pip}」"
        return theme
    name = display_name(card, lang)
    if lang == "ja":
        face = "逆位置" if reversed else "正位置"
    elif lang == "ko":
        face = "역방향" if reversed else "정방향"
    else:
        face = "reversed" if reversed else "upright"
    hint = display_hint(card, reversed, lang)
    if lang == "ja":
        return f"牌名：{name}（{face}）。\n画面の手がかり：{hint}\nこの絵から話す。牌の名前を変えない。"
    if lang == "ko":
        return f"카드 이름: {name} ({face}).\n그림의 단서: {hint}\n이 그림으로 말한다. 카드 이름을 바꾸지 않는다."
    return (
        f"Card name: {name} ({face}).\n"
        f"Picture cue: {hint}\n"
        "Speak from this picture. Use this card name. Do not say Wands as staves, Cups as chalices in another language, "
        "or Pentacles as coins in Chinese."
    )


_EN_MAJOR = [
    "The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor",
    "The Hierophant", "The Lovers", "The Chariot", "Strength", "The Hermit",
    "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance",
    "The Devil", "The Tower", "The Star", "The Moon", "The Sun", "Judgement", "The World",
]
_JA_MAJOR = [
    "愚者", "魔術師", "女教皇", "女帝", "皇帝", "教皇", "恋人", "戦車", "力", "隠者",
    "運命の輪", "正義", "吊るされた男", "死神", "節制", "悪魔", "塔", "星", "月", "太陽", "審判", "世界",
]
_KO_MAJOR = [
    "바보", "마법사", "여사제", "여황제", "황제", "교황", "연인", "전차", "힘", "은둔자",
    "운명의 수레바퀴", "정의", "매달린 사람", "죽음", "절제", "악마", "탑", "별", "달", "태양", "심판", "세계",
]
_SUIT_NAME = {
    "en": {"wands": "Wands", "cups": "Cups", "swords": "Swords", "coins": "Pentacles"},
    "ja": {"wands": "ワンド", "cups": "カップ", "swords": "ソード", "coins": "ペンタクル"},
    "ko": {"wands": "완드", "cups": "컵", "swords": "소드", "coins": "펜타클"},
}
_PIP_NAME = {
    "en": {"01": "Ace", "02": "Two", "03": "Three", "04": "Four", "05": "Five",
           "06": "Six", "07": "Seven", "08": "Eight", "09": "Nine", "10": "Ten",
           "page": "Page", "knight": "Knight", "queen": "Queen", "king": "King"},
    "ja": {"01": "エース", "02": "2", "03": "3", "04": "4", "05": "5",
           "06": "6", "07": "7", "08": "8", "09": "9", "10": "10",
           "page": "ペイジ", "knight": "ナイト", "queen": "クイーン", "king": "キング"},
    "ko": {"01": "에이스", "02": "2", "03": "3", "04": "4", "05": "5",
           "06": "6", "07": "7", "08": "8", "09": "9", "10": "10",
           "page": "페이지", "knight": "나이트", "queen": "퀸", "king": "킹"},
}
_PIP_HINT_EN = {
    "01": ("a start, the spark just up", "still at the door"),
    "02": ("two sides, not chosen yet", "wanting both"),
    "03": ("something is taking shape", "the small gathering loosened"),
    "04": ("a place to rest and hold", "so steady it needs a window"),
    "05": ("a tangle, a little fight", "the fight is still stuck"),
    "06": ("a breath, a hand offered", "old comfort held too long"),
    "07": ("still weighing it", "lots of thought, one small step"),
    "08": ("time to move, not only think", "one knot undone is enough"),
    "09": ("close, and heavier", "worry at the last stretch"),
    "10": ("this stretch is done", "the load is heavy, set one thing down"),
    "page": ("just learning the suit", "the news is not all in yet"),
    "knight": ("already moving", "moving a bit too hard"),
    "queen": ("she knows what she feels", "feeling is full"),
    "king": ("someone has to carry it", "the weight can be shared"),
}


def _rank_id(card: Card) -> str:
    cid = str(card.get("id") or "")
    return cid.split("/", 1)[-1].split("-", 1)[0] if "/" in cid else ""


def display_name(card: Card, lang: str) -> str:
    from ...locale_pack import normalize
    lang = normalize(lang)
    if lang == "zh-CN":
        return str(card.get("name") or "")
    cid = str(card.get("id") or "")
    if cid.startswith("major/"):
        try:
            idx = int(cid.split("/")[1].split("-")[0])
        except ValueError:
            idx = -1
        table = {"ja": _JA_MAJOR, "ko": _KO_MAJOR}.get(lang, _EN_MAJOR)
        if 0 <= idx < len(table):
            return table[idx]
        return str(card.get("name") or "")
    suit_key = str(card.get("suit") or "")
    suits = _SUIT_NAME.get(lang, _SUIT_NAME["en"])
    pips = _PIP_NAME.get(lang, _PIP_NAME["en"])
    rank = _rank_id(card)
    suit = suits.get(suit_key, suit_key)
    pip = pips.get(rank, rank)
    if lang == "ja":
        return f"{suit}の{pip}"
    if lang == "ko":
        return f"{suit}의 {pip}"
    return f"{pip} of {suit}"


def display_hint(card: Card, reversed: bool, lang: str) -> str:
    rank = _rank_id(card)
    pair = _PIP_HINT_EN.get(rank)
    if pair:
        return pair[1] if reversed else pair[0]
    if str(card.get("arcana") or "") == "major":
        return "the picture on this major arcana card"
    return "the picture of this card"


def enrich(card: Card) -> Card:
    rel = str(card.get("file") or "")
    item = dict(card)
    item["has_art"] = has_art(rel)
    item["url"] = f"/assets/tarot/{rel}" if rel else ""
    item["back_url"] = "/assets/tarot/back.png"
    item["back_ready"] = back_exists()
    return item
