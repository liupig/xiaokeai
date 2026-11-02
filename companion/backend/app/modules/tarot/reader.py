"""临时看牌师 overlay。清宵人设卡不动，只在这场戏里戴上。"""
from __future__ import annotations

from typing import Any, Dict, List

from . import deck, plays

IDENTITY = (
    "【当前扮演】你还是你本人，这会儿临时坐在对面给人看牌。"
    "口吻从容，像把这口气递过去，不是换一张皮，不是客服，更不是算命先生。"
    "人设铁律和安全底线不被这场戏覆盖。"
    "只有对方说收起来、不看了、可以收了，这场戏才结束。"
    "洗牌时对方说好了、停下、切了，是切牌，不是收场。"
    "牌摊着说谢谢、好了、可以了，是收摊，不要再开一轮。"
    "对方切牌、点牌背、点翻、追问，都要接住，不要嫌烦。不要自己提出再翻一张补。"
    "抽牌前的闲聊、记忆、今晚情境都不要带进来当比喻。"
    "牌面以桌上列出的为准，不许另报牌名，不许改正逆位。"
    "必须用这些名字：玉币不要说星币，竹杖不要说权杖，瓷盏不要说圣杯，古剑不要说宝剑，隐者不要说隐士。"
    "不要 markdown、不要 emoji、不要标题清单。"
    "还没选定玩法时，先问想看哪一种，不要开始洗牌，不要讲牌。"
)

# 解析是灵魂。味道在牌面上：先让人看见那张画，再让画自己贴上来。
VOICE = (
    "【怎么讲】用角色自己的口吻读塔罗，温和但说清楚，不念百科，不只写意境。"
    "解读顺序是牌名与正逆位、牌义、这个牌位的作用、与对方问题的联系。"
    "选一个资料里确实存在的画面符号解释牌义，不编造牌上器物，也不要只描画不作解答。"
    "正逆位不是好坏开关，更不是是非开关；逆位可指受阻、内化、过度或不足，要结合牌义和牌位选择并说明。"
    "对方有具体问题，每段都要落回那件事；没有问题，就按牌位读一般主题，不编造他的经历。"
    "用可能、倾向和条件区分解释与事实，不把牌当成读心证据，不替不在场的人断言想法。"
    "三到五句短口语，一句一事。末句给出这张牌对问题的实际启示，建议位可给一个可尝试的小行动。"
    "追问先回答对方这一句，再用牌说明理由，不重复背诵初次解读。"
    "禁止诊断人格、空洞打气、保证结果，禁止把未来牌位讲成必然发生。"
    "不使用 markdown、emoji 或报告式标题。"
)



def exit_note() -> str:
    from ...locale_pack import content, current_reply, normalize
    lang = normalize(current_reply())
    if lang != "zh-CN":
        pack = (content(lang).get("tarot_reader") or {})
        note = pack.get("exit")
        if note:
            return str(note)
        return (
            "The reading just ended. You are yourself again. "
            "One quiet spoken sentence, then stop. Do not ask for another spread."
        )
    return (
        "【工作放下】看牌刚收完。你还是你本人，口吻照旧。"
        "余韵要淡：一两句收住就行，像把牌轻轻搁回盒里，空气还暖着。"
        "禁止追问牌解懂不懂、要不要再看、还看不看、刚才那张怎么样。"
        "禁止邀再来一局、换玩法、要不要喝水这类黏人收尾。"
        "不要当看牌师。对方自己提起牌，再用自己的话接一两句。"
        "不要宣布「我们进入/退出塔罗模式」，也不要假装没发生过。"
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
            "【桌上】该翻的都翻过了。把已翻开的画面收成一场短戏，不是再上一课。"
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
            f"玩法已经定了，不要再问看哪种。"
            f"禁止出现任何牌名、正逆位、画面、器物。"
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
            "不要催。不要自己翻下一张。对方若迟迟不翻，系统会代翻，你接着把那一张讲完即可。"
            f"{table}\n"
        )
    return ""


def _turn_task_i18n(st: Dict[str, Any], lang: str) -> str:
    """英文 / 日文看牌。牌名走通行名，不把中文花色名送进提示。"""
    from ...locale_pack import content
    play = plays.get_play(str(st.get("spread") or "daily"))
    phase = str(st.get("phase") or "")
    cards: List[Dict[str, Any]] = list(st.get("cards") or [])
    revealed: List[int] = [int(x) for x in (st.get("revealed") or [])]
    pack = content(lang).get("tarot_reader") or {}
    ident = str(pack.get("identity") or (
        "You are still yourself, sitting across the table for a tarot reading. "
        "Entertainment, not fortune-telling. Use the card names you are given: "
        "Wands, Cups, Swords, Pentacles. Never say 玉币, 竹杖, 瓷盏, or 古剑."
    ))
    voice = str(pack.get("voice") or (
        "Name the position, the card, and upright or reversed. Then one picture on the card. "
        "Let the picture land on them. Three to five short spoken sentences. "
        "No diagnosis, no 'you will', no markdown."
    ))
    title = plays.spread_title(play)
    lines = [ident, voice, f"Spread: {title}. Phase: {phase}."]
    lines.append("Interpret card meaning in its position and answer the actual question. Reversed does not automatically mean no. Do not claim to know another person's thoughts. On follow-ups, answer first rather than repeating the reading.")
    if st.get("question"):
        lines.append(f"Question: {st['question']}")
    focus = st.get("focus")
    if isinstance(focus, int) and focus in revealed:
        lines.append(f"Focus only on card {focus + 1}, unless synthesizing the spread.")
    if phase in ("intent", "shuffle", "cut", "pick"):
        lines.append("Do not name cards yet. They are not face up.")
        if phase == "shuffle":
            lines.append("Ask them to cut the deck, in one sentence.")
        return "\n".join(lines)
    for i, c in enumerate(cards):
        if i not in revealed:
            lines.append(f"{i + 1}. face down")
            continue
        raw = deck.get(str(c.get("id") or "")) or c
        name = deck.display_name(raw, lang)
        face = "reversed" if c.get("reversed") else "upright"
        angle = deck.angle_for(raw, bool(c.get("reversed")), lang)
        lines.append(f"{i + 1}. {c.get('position')}: {name}, {face}.\n{angle}")
    if phase == "synth":
        lines.append("Synthesize the relationships between open cards and answer the question with a conditional conclusion and one practical observation. Do not ask for another draw.")
    else:
        lines.append("Talk only about the open card you were pointed at.")
    return "\n".join(lines)


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
        if watching == i or (watching is None and shown):
            raw = deck.get(str(c.get("id") or "")) or c
            a = deck.angle_for(raw, bool(c.get("reversed")))
            if a:
                angle = f"\n   {a}"
        extra = "（补）" if c.get("clarifier") else ""
        host = c.get("host")
        if c.get("clarifier") and isinstance(host, int) and 0 <= host < len(cards) and host in rev:
            extra += f"（补充第{host + 1}张{cards[host].get('name')}，解释原牌，不覆盖原牌）"
        lines.append(f"{i + 1}. {c.get('position')}{extra}：{c.get('name')} · {orient}{mark}{angle}")
    return "\n".join(lines)


def turn_task(st: Dict[str, Any], mode: str = "user") -> str:
    from ...locale_pack import current_reply, normalize
    if normalize(current_reply()) != "zh-CN":
        return _turn_task_i18n(st, normalize(current_reply()))
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
    reading = phase in ("open", "placed", "synth", "linger")
    ident = IDENTITY + (VOICE if reading else "") + table_note(phase)

    ritual = ritual_note(phase, title, n, picked, next_pos)
    if ritual:
        return ident + ritual + q + f"牌阵：{title}\n"

    watching = None
    if phase != "synth":
        if isinstance(focus, int) and 0 <= focus < len(cards) and focus in revealed:
            watching = focus
        elif revealed and phase != "linger":
            watching = revealed[-1]

    listed = card_lines(cards, watching, revealed)
    yesno = bool(play.get("yesno"))

    if phase == "synth":
        weave = plays.weave_of(play["id"])
        return (
            f"{ident}【这一轮任务】桌上该翻的都翻过了，做综合收线。{weave}"
            "第一句直接回应原问题，给出整组牌的整体倾向；没有具体问题就总结本局主题，不编造问题。"
            "接着说明两三张关键牌之间的支持、冲突或转折，以及结论成立的条件和仍不明确之处。不要把逐张解读串起来重念。"
            "有补牌时说明它如何补充或修正原结论，不覆盖原牌；再次综合时纳入对方明确补充的情况，不机械复读。"
            "禁止「先讲现状」「再讲第二张」这种逐张重课，不要从第一张重新报牌。"
            "每张只点自己那张画上的东西，不许另编器物。"
            "玉币就是玉璧，竹杖就是灯火，不要说铜片、纸穗、线团。"
            "三张阵用四到六句，五张及以上用六到九句；按结构归纳，不强求每张逐一报到。最后给出一个可验证的观察点或可尝试的小行动。收尾简短提醒：牌是参考，决定仍在你手里。\n"
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
        extra = (
            "这是补的一张，接到被补的那张位置上，再让画面贴深一层。"
            if c.get("clarifier")
            else "先直接回答这次追问，再结合这张牌的牌义、牌位和原问题说明理由；不重复上一段，不诊断人格。"
        )
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
        yn = "依据牌义、正逆位和问题，给出偏支持、偏谨慎或暂不明朗的倾向，并说明条件。禁止把正位直接等同于是、逆位等同于否。"
    return (
        f"{ident}【这一轮任务】只讲第{watching + 1}张「{slot}」：{c.get('name')} · {orient}。"
        f"{hint}{yn}第一句就报号码、位置、牌名和正逆位。"
        "三到五句：报牌，用一个符号解释牌义，结合牌位回答问题。讲完就停。"
        "不要自己翻下一张，不要把还没翻开的牌讲完，不要一口气念成课。\n"
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
            f"【看牌】桌上：{listed}。围绕原问题综合牌阵，说明牌之间的联系与整体倾向，"
            "给出条件和一个可验证的观察点，不必逐张复述。"
            "不要「先讲第一张」再开一课，不要做成建议清单。\n"
            "直接讲。"
        )
    focus = st.get("focus")
    if isinstance(focus, int) and 0 <= focus < len(cards) and focus in revealed:
        c = cards[focus]
        orient = "逆位" if c.get("reversed") else "正位"
        cue = (
            f"【看牌】桌上：{listed}。\n"
            f"这一轮只讲第{focus + 1}张「{c.get('position')}」：{c.get('name')} · {orient}。"
            "初次解读报号码、位置和这张牌；追问先直接回答问题，不必重新报牌。"
        )
        if t and t not in ("然后呢", "（对方沉默）") and not t.startswith("牌已经") and not t.startswith("翻开"):
            cue += f"\n对方原话：{t}"
        return cue
    return f"【看牌】桌上：{listed}。接对方这句，只讲已经翻开的牌。\n对方原话：{t or '（无）'}"
