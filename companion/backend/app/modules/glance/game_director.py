"""Game commentary cadence. Mechanics are evidence; emotion is the character's."""
from __future__ import annotations

import re


def priority(phase: str, text: str) -> str:
    if phase == "score":
        return "result"
    if phase == "dead":
        return "death"
    if re.search(r"击杀|双杀|三杀|四杀|五杀|抢到|拿下|推掉|命中|打中|躲开|逃脱|丝血", text):
        return "highlight"
    return "routine"


def cadence(phase: str, text: str, *, talk: str, elapsed: float, opening: bool, same_phase: bool = False, identity_changed: bool = False) -> bool:
    if talk == "quiet":
        return False
    if identity_changed:
        return True
    if same_phase and phase in {"dead", "score"}:
        return False
    if opening or priority(phase, text) != "routine":
        return True
    gap = 12 if talk == "more" else 25
    return elapsed >= gap


def direction(phase: str, text: str) -> str:
    mode = priority(phase, text)
    if mode == "death":
        return "先轻轻接他倒下的这一下，不责怪。倒计时来自截图，别当成当前秒数报。不要重复安慰。"
    if mode == "result":
        return "这局结束了。结果确认才庆祝或遗憾，可以提刚才确实发生的一件事。不要编战绩。"
    if mode == "highlight":
        return "就接这个已经确认的瞬间，短短一句，有情绪。别复述整段画面，别编后续。"
    if phase == "fight":
        return "交战中短短接一句，不提问题，不要求他分心回答，不喊操作指令。"
    return "像坐在旁边陪他，接他刚说的目标或这一下变化。同一件事已经说过就安静。"


def unsupported_reply(evidence: str, spoken: str) -> str:
    """Do not let character flavor invent a kill, an opponent or a tactical order."""
    for word in ("秒人", "秒了", "单杀", "双杀", "三杀", "四杀", "五杀", "抢龙", "大龙", "小龙", "闪现", "大招", "超神", "连杀"):
        if word in spoken and word not in evidence:
            return f"未确认{word}"
    if re.search(r"你往后|往后挪|往后撤|撤一下|快后撤|快退|别硬扛|你.*应该|你盯着她|宝你盯着她", spoken):
        return "没有战术依据，不要发操作指令"
    if "装备栏" in spoken and any(word in spoken for word in ("空", "没买")) and "装备栏为空" not in evidence:
        return "没读到装备不等于装备栏为空"
    from ..sight.screen_text import champions

    for item in champions().values():
        name = item["title"]
        if len(name) >= 2 and name in spoken and name not in evidence:
            return "提到了未确认的英雄"
    return ""


async def grounded_reply(conf: dict, messages: list[dict], *, evidence: str, topic: str, valid=lambda: True, scene: str = "game", stream=None) -> dict:
    """Shared by the live route and real-model replay. At most one repair."""
    import asyncio
    from contextlib import aclosing
    from ...services.llm import stream_chat
    from .watch import hollow_company, parse_reaction
    generate = stream or stream_chat

    turns = list(messages)
    if scene in {"movie", "video", "music"}:
        from ...locale_pack import current_reply
        from ..sight.media_language import reply_rule
        turns.append({"role": "system", "content": reply_rule(current_reply())})
    attempts = []
    for attempt in range(2):
        pieces, performance, errors = [], [], []
        try:
            async with asyncio.timeout(15):
                async with aclosing(generate(conf, turns)) as source:
                    async for event in source:
                        if not valid():
                            attempts.append({"raw": "".join(pieces), "errors": ["candidate_expired"], "problem": ""})
                            return {"action": "drop", "text": "", "attempts": attempts, "performance": []}
                        if event.get("type") == "text":
                            pieces.append(event.get("delta") or "")
                        elif event.get("type") in {"emo", "intent", "expr"}:
                            performance.append(event)
                        elif event.get("type") == "error":
                            errors.append(event.get("code") or "error")
        except TimeoutError:
            errors.append("generation_timeout")
        raw = "".join(pieces)
        parsed = parse_reaction(raw, topic)
        spoken = parsed[1] if parsed else ""
        if spoken:
            from .conversation import strip_opening
            spoken = strip_opening(spoken)
        if scene in {"movie", "video", "music"}:
            from .media_director import unsupported_reply as check
        else:
            check = unsupported_reply
        problem = check(evidence, spoken) if spoken else ""
        attempts.append({"raw": raw, "errors": errors, "problem": problem})
        if not valid():
            attempts[-1]["errors"].append("candidate_expired")
            return {"action": "drop", "text": "", "attempts": attempts, "performance": []}
        if not raw.strip() and not errors:
            attempts[-1]["errors"].append("empty_reply")
            if attempt == 0:
                turns.append({"role": "user", "content":
                    f"刚才没有返回内容。请就当前已经确认的事实「{evidence}」接一句自然的感受或向对方问一个相关的小问题。不要编造画面或后续。"})
                continue
        if errors or not parsed or parsed[0] == "silent" or not spoken:
            return {"action": "silent", "text": "", "attempts": attempts, "performance": []}
        if problem and attempt == 0:
            turns += [{"role": "assistant", "content": spoken}, {"role": "user", "content":
                f"这句有一处没有依据：{problem}。删除这部分，仅接已确认的事实「{evidence}」。"
                "说一句自然的感受，不描述未知操作，不指挥他，不解释改写过程。"}]
            continue
        action = "unsupported" if problem else "hollow" if hollow_company(spoken) else "speak"
        return {"action": action, "text": spoken if action == "speak" else "", "attempts": attempts,
                "performance": performance if action == "speak" else []}
    return {"action": "silent", "text": "", "attempts": attempts, "performance": []}
