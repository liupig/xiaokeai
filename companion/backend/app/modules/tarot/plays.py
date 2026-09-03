"""看牌玩法表。名字可以很多，交互只有这几套。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

Play = Dict[str, Any]

PLAYS: List[Play] = [
    {
        "id": "daily",
        "group": "quick",
        "title": "日抽一张",
        "n": 1,
        "layout": "row",
        "positions": ("今日",),
        "hints": {
            "今日": "抓重点讲眼下这口气，再补一句可以动手的小提醒。",
        },
        "weave": "这一张就是今日的口气。收尾带一句仅供娱乐。",
        "yesno": False,
    },
    {
        "id": "yesno",
        "group": "quick",
        "title": "是否一张",
        "n": 1,
        "layout": "row",
        "positions": ("倾向",),
        "hints": {
            "倾向": "正位偏「更值得往这边靠」，逆位偏「先别硬推」。讲倾向和为什么，不是天命判决。",
        },
        "weave": "把倾向收成一句人话。禁止「一定会 / 绝对不行」。",
        "yesno": True,
    },
    {
        "id": "three",
        "group": "three",
        "title": "时间线三张",
        "n": 3,
        "layout": "row",
        "positions": ("过去", "现在", "未来"),
        "hints": {
            "过去": "造成现状的根源：旧底、已经发生的习惯。现在和未来先按着。",
            "现在": "当下真实处境。要接到过去，不是另起一段。",
            "未来": "若维持当下，可能演化的走向，不是定死结局。禁止「一定会」。",
        },
        "weave": "把三张收成一条因果：过去如何铺到现在，现在的选择会如何改未来的趋势。未来不是注定。",
        "yesno": False,
    },
    {
        "id": "advice",
        "group": "three",
        "title": "行动三张",
        "n": 3,
        "layout": "row",
        "positions": ("现状", "阻碍", "建议"),
        "hints": {
            "现状": "目前局面：心态加外在。阻碍和建议先按着。",
            "阻碍": "困住他的关键点。接到现状，建议先按着。",
            "建议": "收成可以做的一两步人话，不是命令。接到阻碍。",
        },
        "weave": "现状是什么样，阻碍卡在哪，建议变成一两句能做的人话。点明矛盾，不要玄虚。",
        "yesno": False,
    },
    {
        "id": "body",
        "group": "three",
        "title": "身心三张",
        "n": 3,
        "layout": "row",
        "positions": ("心", "身", "气"),
        "hints": {
            "心": "念头和心情眼下卡在哪。身和气先按着。",
            "身": "体力、节奏、手头的事。接到心。",
            "气": "整个人的松紧。接到心和身，给一个能缓一口气的小动作。",
        },
        "weave": "心、身、气收成一个当下状态，给一句能动手的提醒。",
        "yesno": False,
    },
    {
        "id": "bond",
        "group": "five",
        "title": "关系五张",
        "n": 5,
        "layout": "row",
        "positions": ("我", "对方", "连接", "卡住", "潜力"),
        "hints": {
            "我": "我这边此刻的位置和心情。",
            "对方": "对方这边能看见的态度，不是读心。",
            "连接": "两人中间正在发生的事。",
            "卡住": "关系里发紧的那一点。",
            "潜力": "若两边都松一点，可能长出什么。不是预言结局。",
        },
        "weave": "把五张收成关系里的一张地图：两边各站哪、中间是什么、卡在哪、可以往哪松。",
        "yesno": False,
    },
    {
        "id": "work",
        "group": "five",
        "title": "事业五张",
        "n": 5,
        "layout": "row",
        "positions": ("现状", "优势", "挑战", "机会", "行动"),
        "hints": {
            "现状": "工作上眼下这口气。",
            "优势": "手里已经有的家伙。",
            "挑战": "真正卡住的点。",
            "机会": "可以伸手的窗口，不是天上掉馅饼。",
            "行动": "一两步能做的人话。",
        },
        "weave": "现状、优势、挑战、机会收成一条可走的路，行动只要一两步。",
        "yesno": False,
    },
    {
        "id": "choice",
        "group": "choice",
        "title": "二选一",
        "n": 7,
        "layout": "choice",
        "positions": ("A现况", "A阻碍", "A走向", "B现况", "B阻碍", "B走向", "总建议"),
        "hints": {
            "A现况": "选 A 时眼前的局面。",
            "A阻碍": "走 A 会顶到的墙。",
            "A走向": "若选 A，可能演化的趋势，不是定局。",
            "B现况": "选 B 时眼前的局面。",
            "B阻碍": "走 B 会顶到的墙。",
            "B走向": "若选 B，可能演化的趋势，不是定局。",
            "总建议": "不替他拍板。把两条路的味道对上，给一句怎么选的人话。",
        },
        "weave": "A、B 两条路分开看完，最后一张只帮他对齐，不替他决定。",
        "yesno": False,
    },
    {
        "id": "celtic",
        "group": "deep",
        "title": "凯尔特十字",
        "n": 10,
        "layout": "celtic",
        "positions": (
            "现况", "挑战", "根", "近过去", "目标",
            "近未来", "自我", "外界", "希望恐惧", "出路",
        ),
        "hints": {
            "现况": "事情此刻的核心。",
            "挑战": "横在正中间的那股劲，可盖可顶。",
            "根": "底下那层旧因。",
            "近过去": "刚发生、还没散干净的。",
            "目标": "他心里想够到的那头。",
            "近未来": "顺着现在走，近处可能碰到什么。",
            "自我": "他自己怎么站在这件事里。",
            "外界": "别人和场面施加的力。",
            "希望恐惧": "盼的和怕的常常是同一件事的两面。",
            "出路": "若维持当下力气，比较可能落到哪。不是命运判决。",
        },
        "weave": "十字看结构和根，右侧一列看人和外界。出路不是天命，是顺着现在走的可能落点。",
        "yesno": False,
    },
]

_BY_ID = {p["id"]: p for p in PLAYS}

ALIASES = {
    "daily": "daily",
    "yesno": "yesno",
    "yes": "yesno",
    "no": "yesno",
    "three": "three",
    "timeline": "three",
    "advice": "advice",
    "counsel": "advice",
    "path": "advice",
    "action": "advice",
    "body": "body",
    "mind": "body",
    "bond": "bond",
    "love": "bond",
    "relation": "bond",
    "work": "work",
    "career": "work",
    "job": "work",
    "choice": "choice",
    "either": "choice",
    "celtic": "celtic",
    "cross": "celtic",
}


def get_play(spread: str) -> Play:
    key = ALIASES.get((spread or "").strip().lower(), "daily")
    return _BY_ID[key]


def _compact(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("「", "").replace("」", "").replace("『", "").replace("』", "")
    t = re.sub(r"[\s。！？、,.!?;；…~～\"'“”]+", "", t)
    return t


_CN_NUM = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_idx(raw: str) -> Optional[int]:
    s = (raw or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    return _CN_NUM.get(s)


def _fold_asr(text: str) -> str:
    """选玩法阶段：把常见口误折回标准叫法。不用于开局唤醒。"""
    n = _compact(text)
    n = re.sub(r"[地低弟滴递](?=[一二三四五六七八九十两0-9])", "第", n)
    n = n.replace("章", "张")
    repl = (
        ("是闲聊", "时间线"), ("时间连", "时间线"), ("时见线", "时间线"),
        ("十间线", "时间线"), ("时见连", "时间线"), ("时间联", "时间线"),
        ("开尔特", "凯尔特"), ("开了特", "凯尔特"), ("凯利特", "凯尔特"),
        ("开二特", "凯尔特"), ("开耳特", "凯尔特"), ("开尔特十字", "凯尔特十字"),
        ("是佛", "是否"), ("是否一章", "是否一张"),
        ("日出一张", "日抽一张"), ("一抽一张", "日抽一张"),
    )
    for a, b in repl:
        n = n.replace(a, b)
    return n


def match_play_ordinal(text: str) -> Optional[str]:
    """『第一个』『第二号』『选3个』按屏幕编号对上玩法。"""
    n = _fold_asr(text)
    t = (text or "").strip()
    if not t:
        return None
    if re.search(r"最后[一个种号款]?", n) or n in ("最后", "最后一个"):
        return str(PLAYS[-1]["id"])
    patterns = (
        r"第\s*([一二三四五六七八九十两0-9]+)\s*(?:个|种|号|款|项|游戏|玩法|张)?",
        r"(?:选|要|用|玩|来)\s*第?\s*([一二三四五六七八九十两0-9]+)\s*(?:个|种|号|款|项)",
        r"([一二三四五六七八九十两0-9]+)\s*号",
    )
    for src in (n, t):
        for pat in patterns:
            m = re.search(pat, src)
            if not m:
                continue
            idx = _parse_idx(m.group(1))
            if idx is None or idx < 1 or idx > len(PLAYS):
                continue
            return str(PLAYS[idx - 1]["id"])
    return None


_ANY_PLAY_RE = re.compile(r"随便|你定|你来选|都可以|都行|随机|你看着办|你挑一个|你看着选")

# 只在「选玩法」相位用，避免日常「你是不是…」误开牌。
_INTENT_YESNO_EXACT = {"是不是", "要不要", "行不行", "是否", "能不能"}

_INTENT_KEYS = (
    ("celtic", ("凯尔特十字", "凯尔特", "十字阵", "大十字")),
    ("choice", ("二选一", "两个选择", "选A还是", "左右为难", "两条路")),
    ("bond", (
        "关系五张", "感情五张", "关系阵", "感情阵", "关系五", "感情五",
        "四页五张", "四页",
    )),
    ("work", ("事业五张", "工作五张", "事业阵", "工作阵", "事业五", "工作五", "职场")),
    ("body", ("身心三张", "身心", "心身体", "状态三张")),
    ("advice", ("行动三张", "建议阵", "行动阵", "阻碍建议", "怎么做阵", "现状阻碍")),
    ("three", (
        "时间线三张", "时间线", "过去现在未来", "三张阵", "三张塔罗",
        "来三张", "抽三张", "要三张", "选三张", "三张牌", "来个三张",
    )),
    ("yesno", ("是否一张", "抽一张看是否", "看是否")),
    ("daily", ("日抽一张", "日抽", "今日牌")),
)


def resolve_play_choice(text: str) -> Optional[str]:
    """选玩法：点名优先，其次第几个，再兜口误。"""
    folded = _fold_asr(text)
    hit = match_play_id(text) or match_play_id(folded)
    if hit:
        return hit
    hit = match_play_ordinal(text)
    if hit:
        return hit
    n = folded or _compact(text)
    if n in _INTENT_YESNO_EXACT:
        return "yesno"
    for pid, words in _INTENT_KEYS:
        if any(w and w in n for w in words):
            return pid
    if re.search(r"四页|关系五|感情五", n):
        return "bond"
    if re.search(r"事业五|工作五", n):
        return "work"
    if _ANY_PLAY_RE.search(text) or n in ("随便", "都行", "都可以", "随机"):
        return "three"
    return None


def match_play_id(text: str) -> Optional[str]:
    """从口语里认出玩法。先对标题，再对常用叫法。开局唤醒也走这里，别放太宽。"""
    n = _compact(text)
    if not n:
        return None
    ranked = sorted(PLAYS, key=lambda p: len(str(p.get("title") or "")), reverse=True)
    for p in ranked:
        title = _compact(str(p.get("title") or ""))
        if title and title in n:
            return str(p["id"])
    aliases = (
        ("celtic", ("凯尔特", "十字阵", "大十字", "十张")),
        ("choice", ("二选一", "两个选择", "选A还是", "左右为难", "两条路")),
        ("bond", (
            "关系阵", "感情阵", "关系五张", "关系五章", "感情五张", "感情五章",
            "四页五章", "四页五张", "四页5章", "四页5张", "关系5张", "关系5章",
        )),
        ("work", ("事业阵", "工作阵", "事业五张", "事业五章", "工作五张", "职场")),
        ("body", ("身心", "心身体", "身心三张", "身心三章", "状态三张")),
        ("advice", ("行动三张", "行动三章", "建议阵", "行动阵", "怎么做阵")),
        ("yesno", ("是否一张", "抽一张看是否")),
        ("three", ("时间线", "过去现在未来", "三张阵", "三张塔罗", "来三张", "抽三张", "三张牌", "时间线三章")),
        ("daily", ("日抽", "今日牌", "抽一张", "来一张")),
    )
    for pid, words in aliases:
        if any(w and w in n for w in words):
            return pid
    return None


def normalize_spread(spread: str) -> str:
    return get_play(spread)["id"]


def list_plays() -> List[Dict[str, Any]]:
    out = []
    for i, p in enumerate(PLAYS):
        out.append({
            "id": p["id"],
            "group": p["group"],
            "title": p["title"],
            "n": p["n"],
            "layout": p["layout"],
            "positions": list(p["positions"]),
            "index": i + 1,
        })
    return out


def slot_hint(spread: str, position: str) -> str:
    play = get_play(spread)
    return str((play.get("hints") or {}).get(position) or "按这个位置讲处境，再落到人身上。")


def weave_of(spread: str) -> str:
    return str(get_play(spread).get("weave") or "收成一条线，点明矛盾和转机。")


def fan_size(spread: str) -> int:
    n = int(get_play(spread)["n"])
    return max(12, min(22, n + 10))


def celtic_xy(i: int) -> Tuple[float, float]:
    """本地坐标，单位约一张牌宽。"""
    table = {
        0: (0.0, 0.0),
        1: (0.08, 0.12),
        2: (0.0, -0.34),
        3: (-0.34, 0.0),
        4: (0.0, 0.34),
        5: (0.34, 0.0),
        6: (0.78, -0.42),
        7: (0.78, -0.14),
        8: (0.78, 0.14),
        9: (0.78, 0.42),
    }
    return table.get(i, (0.0, 0.0))


def choice_xy(i: int) -> Tuple[float, float]:
    table = {
        0: (-0.42, 0.28),
        1: (-0.42, 0.0),
        2: (-0.42, -0.28),
        3: (0.42, 0.28),
        4: (0.42, 0.0),
        5: (0.42, -0.28),
        6: (0.0, -0.02),
    }
    return table.get(i, (0.0, 0.0))
