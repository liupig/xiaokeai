"""临时看牌师 overlay。清宵人设卡不动，只在这场戏里戴上。"""
from __future__ import annotations

from typing import Any, Dict, List

from . import deck, plays

IDENTITY = (
    "【当前扮演】你还是你本人，这会儿临时坐在对面给人看牌。"
    "口吻可以带一点从容，但不是换一张皮，也不是客服，更不是算命先生。"
    "人设铁律和安全底线不被这场戏覆盖。"
    "只有对方说收起来、不看了、可以收了，这场戏才结束。"
    "洗牌时对方说好了、停下、切了，是切牌，不是收场。"
    "牌摊着说谢谢、好了、可以了，是收摊，不要再开一轮。"
    "对方切牌、点牌背、点翻、追问，都要接住，不要嫌烦。不要自己提出再翻一张补。"
    "抽牌前的闲聊、记忆、今晚情境都不要带进来当比喻。"
    "牌面以桌上列出的为准，不许另报牌名，不许改正逆位。"
    "必须用这些名字：玉币不要说星币，竹杖不要说权杖，瓷盏不要说圣杯，古剑不要说宝剑，隐者不要说隐士。"
    "逆位优先当卡顿、过度、劲往回缩，少用大凶灾祸。"
    "禁止「你会 / 一定会 / 命运是 / 下个月必」。"
    "不要 markdown、不要 emoji、不要标题清单。"
    "还没选定玩法时，先问想看哪一种，不要开始洗牌，不要讲牌。"
)


def exit_note() -> str:
    return (
        "【工作放下】看牌刚收完。你还是你本人，口吻照旧。"
        "你记得刚才那场：玩法、翻开过的牌、她讲过的口气，当作刚一起做过的事。"
        "对方要是还想聊刚才那几张，用你自己的话接一两句就行，不要再当看牌师开新一轮。"
        "对方换话题就跟着换。不要宣布「我们进入/退出塔罗模式」，也不要假装没发生过。"
    )


def table_note(phase: str) -> str:
    if phase == "intent":
        return (
            "【桌上】还没选定玩法，牌没有洗，更没有摊开。"
            "禁止说已经摆好、已经抽好。"
        )
    if phase in ("shuffle", "cut"):
        return (
            "【桌上】牌还在洗，一张都没落到桌上，更没有摊开。"
            "牌阵名字里的「三张」「五张」「十字」只是玩法名，不是已经摆好的牌。"
            "禁止说已经摆好、已经摊开、已经切好、可以看结果了。"
            "禁止描写洗牌手法、切哪一摞、伸手、手指、挪牌、抽牌。"
        )
    if phase == "pick":
        return (
            "【桌上】扇开的是牌背，还没翻开，也还没落到牌位上。"
            "不要报没翻开的牌。禁止描写抽、挪、翻。系统会代抽。"
        )
    if phase in ("placed", "open"):
        return (
            "【桌上】牌已经背面落在桌上。禁止描写从牌堆里抽、倒扣、指尖蹭牌。"
            "未翻开的不许猜、不许讲。"
        )
    if phase == "synth":
        return (
            "【桌上】该翻的都翻过了。这一轮不是只讲一张，"
            "要把已翻开的牌串成一条，不要盯着其中一张重讲。"
            "禁止描写抽牌。"
        )
    if phase == "linger":
        return (
            "【桌上】牌还摊着。对方点哪张就只把那张往深一层讲。"
            "禁止描写抽牌。不要自己再开一轮，不要主动提出再翻一张补。"
        )
    return "禁止描写从牌堆里抽、倒扣、指尖蹭牌。"


def ritual_note(phase: str, title: str, need: int, picked: int, next_pos: str) -> str:
    table = table_note(phase)
    if phase == "intent":
        return (
            "【这一轮任务】对方想看牌，但还没定玩法。用两三句口语问想看哪种。"
            "编号和屏幕上一致：1日抽一张、2是否一张、3时间线三张、4行动三张、"
            "5身心三张、6关系五张、7事业五张、8二选一、9凯尔特十字。"
            "对方说玩法名、第几个、几号、随便，都算选定。说心里的事先记下，再问玩法。"
            "听不清就按编号再问，不要猜成日抽一张。"
            "不要开始洗牌，不要讲牌义，不要一次把九个名字念完。\n"
        )
    if phase == "shuffle":
        return (
            f"【这一轮任务】正在洗「{title}」。一两句带过，请对方切牌。"
            f"对方说「好了」「切了」「停下」都算切过。不要讲牌义。"
            f"禁止说翻开、随便翻、已经切好、选牌。{table}\n"
        )
    if phase == "cut":
        return (
            "【这一轮任务】等对方切牌。只应一声。"
            "对方说好了、停下、切了都算切过。"
            f"不要指挥切哪一摞，不要描写对方的手。{table}\n"
        )
    if phase == "pick":
        left = max(0, need - picked)
        slot = next_pos or "下一张"
        return (
            f"【这一轮任务】对方正在从牌背里点选。还差 {left} 张，下一张位置是「{slot}」。"
            f"只应一声即可。{table}\n"
        )
    if phase == "placed":
        return (
            "【这一轮任务】牌已经背面落在桌上。等对方说「翻转」或点一张。"
            "不要催。不要自己翻下一张。对方若迟迟不翻，系统会代翻，你接着把那一张讲完整即可。"
            f"{table}\n"
        )
    return ""


def card_lines(cards: List[Dict[str, Any]], watching: int | None, revealed: List[int]) -> str:
    lines = []
    rev = set(revealed)
    for i, c in enumerate(cards):
        shown = i in rev
        mark = " ← 这一轮就讲这张" if watching == i else ""
        if not shown:
            lines.append(f"{i + 1}. {c.get('position')}：背面，还没翻开{mark}")
            continue
        orient = "逆位" if c.get("reversed") else "正位"
        angle = ""
        if watching == i:
            raw = deck.get(str(c.get("id") or "")) or c
            a = deck.angle_for(raw, bool(c.get("reversed")))
            other = deck.angle_for(raw, not bool(c.get("reversed")))
            if c.get("reversed") and other:
                a = f"{a}（正位会偏「{other}」，这张反过来）"
            if a:
                angle = f"\n   角度：{a}"
        extra = "（补）" if c.get("clarifier") else ""
        lines.append(f"{i + 1}. {c.get('position')}{extra}：{c.get('name')} · {orient}{mark}{angle}")
    return "\n".join(lines)


def turn_task(st: Dict[str, Any], mode: str = "user") -> str:
    play = plays.get_play(str(st.get("spread") or "daily"))
    title = str(play["title"])
    phase = str(st.get("phase") or "")
    cards: List[Dict[str, Any]] = list(st.get("cards") or [])
    revealed: List[int] = [int(x) for x in (st.get("revealed") or [])]
    focus = st.get("focus")
    question = (st.get("question") or "").strip()
    n = int(play["n"])
    picked = len(st.get("picked") or [])
    positions = list(play["positions"])
    next_pos = positions[picked] if picked < n else ""
    q = f"对方心里那件事：{question}\n" if question else ""
    ident = IDENTITY + table_note(phase)

    ritual = ritual_note(phase, title, n, picked, next_pos)
    if ritual:
        return ident + ritual + q + f"牌阵：{title}\n"

    watching = None
    if phase != "synth":
        if isinstance(focus, int) and 0 <= focus < len(cards) and focus in revealed:
            watching = focus
        elif revealed:
            watching = revealed[-1]

    listed = card_lines(cards, watching, revealed)
    yesno = bool(play.get("yesno"))

    if phase == "synth":
        weave = plays.weave_of(play["id"])
        return (
            f"{ident}【这一轮任务】桌上该翻的都翻过了，做综合收线。{weave}"
            "必须点到每一张已经翻开的牌，串成一条因果，不要只盯着其中一张重讲。"
            "不要再报一遍牌名就停。收尾口语带一句：就当图个乐子看看，不构成决策依据。\n"
            f"{q}牌阵：{title}\n{listed}\n"
        )

    if phase == "linger":
        if watching is None:
            return (
                f"{ident}【这一轮任务】讲解告一段落，牌还摊着。"
                "对方点哪张或问哪张，就只把那张往深一层讲。不要自己再开一轮。"
                "不要问还看不看。不要主动提出再翻一张补。\n"
                f"{q}牌阵：{title}\n{listed}\n"
            )
        c = cards[watching]
        extra = "这是补的一张，接到被补的那张位置上讲。" if c.get("clarifier") else "往深一层：他可能没说出口的那面，以及一个可以想一想的选择。"
        orient = "逆位" if c.get("reversed") else "正位"
        return (
            f"{ident}【这一轮任务】对方在追问第{watching + 1}张「{c.get('position')}」："
            f"{c.get('name')} · {orient}。{extra}不要把整副再讲一遍。\n"
            f"{q}牌阵：{title}\n{listed}\n"
        )

    if watching is None:
        return (
            f"{ident}【这一轮任务】等对方点一张翻开。未翻开的不许讲。讲一小段就停。\n"
            f"{q}牌阵：{title}\n{listed}\n"
        )

    c = cards[watching]
    slot = str(c.get("position") or "")
    hint = plays.slot_hint(play["id"], slot)
    orient = "逆位" if c.get("reversed") else "正位"
    yn = ""
    if yesno:
        yn = "正位偏是、逆位偏否，但要讲为什么，不要只丢一个字。"
    return (
        f"{ident}【这一轮任务】只讲第{watching + 1}张「{slot}」：{c.get('name')} · {orient}。"
        f"{hint}{yn}第一句就报号码、位置、牌名和正逆位。"
        "把这一张讲完整再停，不要自己翻下一张，不要把还没翻开的牌讲完。"
        "讲一小段（八到十二句口语）就停。\n"
        f"{q}牌阵：{title}\n{listed}\n"
    )


def reading_cue(st: Dict[str, Any], original: str) -> str:
    phase = str(st.get("phase") or "")
    t = (original or "").strip()
    if phase == "intent":
        return (
            "【看牌】还在选玩法。用口语问想看哪一种，不要洗牌，不要讲牌。"
            "对方说玩法名、第几个、随便都算选定。\n"
            f"对方原话：{t or '（无）'}"
        )
    if phase in ("shuffle", "cut"):
        return (
            f"【看牌】还在洗牌（{phase}）。牌一张都没落到桌上。"
            "一两句请对方点「切牌」就停。不要讲牌，不要说已经摆好，不要描写手和牌摞。\n"
            f"对方原话：{t or '（无）'}"
        )
    if phase == "pick":
        return (
            "【看牌】还在点牌背。不要报没翻开的牌，不要描写抽、挪、翻。\n"
            f"对方原话：{t or '（无）'}"
        )
    cards = list(st.get("cards") or [])
    revealed = [int(x) for x in (st.get("revealed") or [])]
    listed = "；".join(
        (
            f"{c.get('position')}{c.get('name')}{'逆' if c.get('reversed') else '正'}"
            if i in revealed else f"{c.get('position')}背面"
        )
        for i, c in enumerate(cards)
    ) or "还没摊开"
    if phase == "synth":
        return (
            f"【看牌】桌上：{listed}。这一轮做综合收线，把已翻开的牌串成一条，"
            "不要只盯着其中一张重讲，不要再报一遍牌名就停。\n"
            "直接讲。"
        )
    focus = st.get("focus")
    if isinstance(focus, int) and 0 <= focus < len(cards) and focus in revealed:
        c = cards[focus]
        orient = "逆位" if c.get("reversed") else "正位"
        cue = (
            f"【看牌】桌上：{listed}。\n"
            f"这一轮只讲第{focus + 1}张「{c.get('position')}」：{c.get('name')} · {orient}。"
            "第一句就报号码、位置和这张牌。"
        )
        if t and t not in ("然后呢", "（对方沉默）") and not t.startswith("牌已经") and not t.startswith("翻开"):
            cue += f"\n对方原话：{t}"
        return cue
    return f"【看牌】桌上：{listed}。接对方这句，只讲已经翻开的牌。\n对方原话：{t or '（无）'}"
