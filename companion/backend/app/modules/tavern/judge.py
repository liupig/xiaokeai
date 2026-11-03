"""XiaO、AI、对面的角色：把这一手交给聊天模型。失败就交回规则里的性格。"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ...services.llm import auth_headers, build_payload

_FACE = {
    "loli": "萝莉",
    "girl": "少女",
    "lady": "御姐",
    "pup": "犬系",
    "boy": "正太",
    "sire": "爹系",
    "mei": "魅",
    "ying": "影",
    "萝莉": "loli",
    "少女": "girl",
    "御姐": "lady",
    "犬系": "pup",
    "正太": "boy",
    "爹系": "sire",
}
_SYSTEM = """你在魅影酒馆替一名玩家决定这一手。只输出一行 JSON，不要 markdown，不要解释，不要表演标记。
这一局能当桌牌的三种，写在局面里，只能指定那三种，键名用局面里的英文 id。魅和影出什么都算这张桌牌。
你看不见别人的牌。一次只能出自己手里的 1 到 3 张。没有上一手时不能揭穿。
要指定下一轮桌牌时，输出 {"face":"loli","line":"这一轮，萝莉。"}。
要揭穿上一手时，输出 {"act":"call","line":"我不信。"}。
要跟牌时，输出 {"act":"play","cards":["牌的id"],"line":"两张少女，我跟。"}，id 必须来自你自己的手牌。
line 是这个人此刻嘴里说的一句，口语，不超过24个字。不要套固定开头，不要每句都一个样子。
跟牌或先出时，只声称出了几张本轮桌牌，绝不能说出真实花色。
揭穿时说出你为什么不信。定牌时说出你定的花色。
局面里如果指定了台词语言，line 就用那种语言。
这一局你有一个目标，同时给你一段局面分析。两条都要用来决定跟还是揭穿。
目标不是人设，下一局会换，不要因为自己是谁就固定爱揭或爱跟。
分析明显不支持目标时，以分析为准。习性是分析的一部分。"""


def parse_decision(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"\{.*\}", raw, re.S)
    if not fenced:
        return None
    try:
        data = json.loads(fenced.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _allowed(brief: dict[str, Any]) -> set[str]:
    raw = brief.get("faces") or ("loli", "girl", "lady")
    return {str(face) for face in raw}


def _face(value: object, allowed: set[str]) -> str:
    text = str(value or "").strip()
    mapped = _FACE.get(text, text)
    return mapped if mapped in allowed else ""


def _cards(brief: dict[str, Any], raw: object) -> list[str]:
    hand = [str(card) for card in (brief.get("hand") or [])]
    if not isinstance(raw, list):
        return []
    chosen: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text in hand and text not in chosen:
            chosen.append(text)
            continue
        face = _FACE.get(text, text)
        for card in hand:
            if card in chosen:
                continue
            if card.split(":", 1)[0] == face:
                chosen.append(card)
                break
    return chosen[:3]


def _line(data: dict[str, Any]) -> str:
    raw = str(data.get("line") or "")
    cleaned = "".join(ch for ch in raw if ch not in "{}\"[]`")
    cleaned = re.sub(r"(?:loli|girl|lady|pup|boy|sire|mei|ying):\d+", "", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:36]


def _with_line(data: dict[str, Any], found: dict[str, Any]) -> dict[str, Any]:
    line = _line(data)
    if line:
        found["line"] = line
    return found


def normalize(brief: dict[str, Any], text: str) -> dict[str, Any] | None:
    data = parse_decision(text)
    if not data:
        return None
    if brief.get("phase") == "name":
        face = _face(data.get("face") or data.get("suit"), _allowed(brief))
        return _with_line(data, {"face": face}) if face else None
    act = str(data.get("act") or "").strip().lower()
    if act in ("call", "质疑", "揭穿") and brief.get("pile"):
        return _with_line(data, {"act": "call"})
    if act in ("play", "跟", "跟牌", "出牌"):
        cards = _cards(brief, data.get("cards"))
        return _with_line(data, {"act": "play", "cards": cards}) if cards else None
    return None


_LANG_NAME = {"zh-CN": "中文", "en": "English", "ja": "日本語", "ko": "한국어"}

_GOAL = {
    "scrape": "这一局的目标是混苟分。少碰枪，能跟小牌就跟，假牌少出。只有上一手张数多、而且这个人以往爱诈，才揭穿。",
    "safe": "这一局的目标是求稳。真话优先，一次少出。揭穿要有理由。枪已经空响两次，就不要再揭。",
    "push": "这一局的目标是激进。可以混一张假牌，上一手只要不像真话，就倾向揭穿。",
    "win": "这一局的目标是要赢。活到最后和提前出完都算胜利。牌少就想出完；别人枪响过、牌又多，就压他。自己枪快空了就收着。",
    "read": "这一局的目标是只做高智商分析。不凭脾气。张数、枪响次数、这个人以往撒谎的比例，三项一起看。看不清就跟小牌，不赌。",
}


def _read(brief: dict[str, Any], names: dict[str, str]) -> str:
    lines = ["局面分析："]
    pile = brief.get("pile")
    if isinstance(pile, dict):
        n = int(pile.get("n") or 0)
        actor = names.get(str(pile.get("actor") or ""), "上家")
        if n >= 3:
            lines.append(f"{actor}一次扣了{n}张，一次出满，撒谎的可能更高。")
        elif n == 1:
            lines.append(f"{actor}只扣了一张。证据不够时，揭穿是在赌。")
        else:
            lines.append(f"{actor}扣了{n}张，中等。要看这个人以往爱不爱诈。")
    pulls = int(brief.get("pulls") or 0)
    if pulls >= 2:
        lines.append("你的枪已经空响两次，下一发很危险。揭错就轮到你开枪。")
    elif pulls == 1:
        lines.append("你的枪空响过一次，还剩两膛，误揭还承受得起。")
    else:
        lines.append("你的枪还没响过，误揭的代价还小。")
    for seat in brief.get("seats") or []:
        if str(seat.get("id") or "") == str(brief.get("who") or ""):
            continue
        if not seat.get("alive") or seat.get("out"):
            continue
        used = int(seat.get("pulls") or 0)
        if used >= 2:
            name = names.get(str(seat.get("id") or ""), "对方")
            lines.append(f"{name}的枪已经空响{used}次，再逼下去，对方容易出局。")
    lines.append("先出完按先后加50、20、10。离席按先后扣50、30、10。活下来的人和提前出完的人都算胜利。")
    lines.append("目标和局面分析都要看。分析明显不支持目标时，以分析为准。")
    return "\n".join(lines)


def _names(brief: dict[str, Any]) -> dict[str, str]:
    her = str(brief.get("her_name") or "她")
    return {"you": "KE", "qin": "XiaO", "bar": "AI", "her": her}


def _situation(brief: dict[str, Any], voice: str) -> str:
    names = _names(brief)
    who = names.get(str(brief.get("who") or ""), "你")
    allowed = [str(face) for face in (brief.get("faces") or ("loli", "girl", "lady"))]
    named = "、".join(_FACE.get(face, face) for face in allowed)
    table = _FACE.get(str(brief.get("table") or ""), "还没定")
    hand = "、".join(
        f"{card}（{_FACE.get(card.split(':', 1)[0], card)}）" for card in (brief.get("hand") or [])
    ) or "没有牌"
    pulls = int(brief.get("pulls") or 0)
    left = max(1, 3 - pulls)
    goal = _GOAL.get(str(brief.get("goal") or ""), "")
    lang = _LANG_NAME.get(str(brief.get("lang") or "zh-CN"), "中文")
    lines = [
        f"台词用{lang}。",
        f"你扮演{who}。",
        voice.strip()[:220],
        goal,
        _read(brief, names),
        str(brief.get("dossier") or "").strip(),
        f"这一局的三种桌牌：{named}。只能指定这三种。",
        f"第{int(brief.get('round') or 1)}轮。本轮桌牌：{table}。",
        f"你的手牌，只有你看得见：{hand}。",
        f"你的枪已经空响{pulls}次。三膛一颗实弹，实弹还在剩下的{left}膛里，你不知道是哪一膛。",
        "在座的人：",
    ]
    for seat in brief.get("seats") or []:
        name = names.get(str(seat.get("id") or ""), str(seat.get("id") or ""))
        if not seat.get("alive"):
            lines.append(f"- {name}：已经离席。")
        elif seat.get("out"):
            lines.append(f"- {name}：已经出完，不参加后面的新局。")
        else:
            lines.append(f"- {name}：手里{int(seat.get('cards') or 0)}张，枪已空响{int(seat.get('pulls') or 0)}次。")
    pile = brief.get("pile")
    if isinstance(pile, dict):
        actor = names.get(str(pile.get("actor") or ""), "上家")
        lines.append(f"上一手是{actor}扣下的{int(pile.get('n') or 0)}张，牌面盖着。你可以揭穿，也可以跟牌。")
    elif brief.get("phase") == "name":
        lines.append("审批刚结束，这一轮的桌牌还没定。请指定萝莉、少女或御姐。")
    else:
        lines.append("这一轮还没有上一手，不能揭穿，请出 1 到 3 张。")
    return "\n".join(line for line in lines if line)


def decide(conf: dict[str, Any], brief: dict[str, Any], voice: str) -> dict[str, Any] | None:
    who = str(brief.get("who") or "")
    base = str((conf or {}).get("base_url") or "").rstrip("/")
    key = str((conf or {}).get("api_key") or "")
    if not base or not key:
        print(f"[tavern] judge {who} fallback (no model)", flush=True)
        return None
    payload = build_payload(conf, [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _situation(brief, voice)},
    ])
    payload["stream"] = False
    payload["temperature"] = 0.7
    payload["max_tokens"] = 180
    model = str(payload.get("model") or "")
    if "character" not in model.lower() and ("volces.com" in base or "bigmodel.cn" in base):
        payload["thinking"] = {"type": "disabled"}
    def ask(body: dict[str, Any]) -> str:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers=auth_headers(base, key),
            json=body,
            timeout=httpx.Timeout(9.0, connect=4.0),
            trust_env=False,
        )
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
        text = message.get("content") if isinstance(message, dict) else ""
        if isinstance(text, list):
            text = "\n".join(str(item.get("text") or "") for item in text if isinstance(item, dict))
        return str(text or "")

    try:
        text = ask(payload)
        found = normalize(brief, text)
        if not found:
            payload["messages"] = [
                *payload["messages"],
                {"role": "assistant", "content": text[:180] or " "},
                {"role": "user", "content": "只输出一行 JSON。"},
            ]
            text = ask(payload)
            found = normalize(brief, text)
    except Exception as exc:
        print(f"[tavern] judge {who} fallback ({type(exc).__name__})", flush=True)
        return None
    if not found:
        print(f"[tavern] judge {who} fallback (unparsed)", flush=True)
        return None
    label = found.get("act") or found.get("face") or "ok"
    print(f"[tavern] judge {who} -> {label}", flush=True)
    return found


_COLOR = """你在魅影酒馆替桌上的人写此刻要说出口的台词。只输出一行 JSON，不要 markdown，不要解释。
每句都是嘴里说的话，不超过24个字。不要动作，不要旁白，不要解释规则，不要用固定套话，不要每句同一个开头。
跟牌或先出时只报张数和本轮桌牌的名字，不能透露真实花色。
语言用用户指定的那一种，不要夹杂别的语言。
普通事件输出 {"line":"一句"}。
揭穿揭晓输出 {"line":"质疑者这句","verdict":"馆主宣布成败并点名谁做审批","rite":"做审批的人举起枪时说的","end":"空膛或中弹时这个人说的"}。
verdict 必须让人一听就知道质疑成功还是失败。"""


def parse_lines(text: str) -> dict[str, str]:
    data = parse_decision(text)
    if not data:
        bare = _line({"line": text})
        return {"line": bare} if bare else {}
    found: dict[str, str] = {}
    for key in ("line", "verdict", "rite", "end"):
        clipped = _line({"line": data.get(key)})
        if clipped:
            found[key] = clipped
    return found


def _color_user(facts: dict[str, Any]) -> str:
    lang = _LANG_NAME.get(str(facts.get("lang") or "zh-CN"), "中文")
    kind = str(facts.get("kind") or "")
    speaker = str(facts.get("speaker") or "这个人")
    face = str(facts.get("face") or "这张")
    rows = [f"台词语言：{lang}。"]
    if kind == "reveal":
        result = "质疑失败，翻出来全是真话" if facts.get("honest") else "质疑成功，里面有别的牌"
        shot = "这一枪是实弹，人要离席" if facts.get("hit") else "这一枪是空膛，人还坐着"
        rows.append(
            f"{facts.get('caller') or '质疑的人'}揭穿了{facts.get('actor') or '上家'}。"
            f"翻开的牌是{facts.get('cards') or '这几张'}。{result}。"
            f"去做审批的是{facts.get('shooter') or '这个人'}。{shot}。"
        )
        if not facts.get("need_line"):
            rows.append("质疑者已经有自己的台词，line 留空。")
    elif kind == "play":
        verb = "在跟牌" if facts.get("follow") else "在先出"
        rows.append(f"{speaker}{verb}，声称{facts.get('n') or 1}张{face}。不能说真实花色。")
    elif kind == "name":
        rows.append(f"{speaker}把这一轮的桌牌定成{face}。")
    elif kind == "deal":
        seated = facts.get("seated") or ""
        dealt = "刚发了牌" if facts.get("dealt") else "牌没有重发"
        rows.append(f"馆主在宣布。本轮桌牌是{face}。先手是{speaker}。还坐着的有{seated}。{dealt}。")
    elif kind == "clear":
        rows.append(f"{speaker}把手里的牌出完了，没有人揭穿。")
    elif kind == "win":
        rows.append(f"这一局结束。{speaker}留到了最后。")
    else:
        rows.append(f"{speaker}要说一句。")
    return "\n".join(rows)


def color(conf: dict[str, Any], facts: dict[str, Any]) -> dict[str, str] | None:
    """给这一手里还没有人话的地方补一句。模型没有就返回空，调用方留着兜底。"""
    kind = str(facts.get("kind") or "")
    if kind not in ("play", "name", "deal", "clear", "win", "reveal"):
        return None
    base = str((conf or {}).get("base_url") or "").rstrip("/")
    key = str((conf or {}).get("api_key") or "")
    if not base or not key:
        return None
    payload = build_payload(conf, [
        {"role": "system", "content": _COLOR},
        {"role": "user", "content": _color_user(facts)},
    ])
    payload["stream"] = False
    payload["temperature"] = 0.9
    payload["max_tokens"] = 220
    model = str(payload.get("model") or "")
    if "character" not in model.lower() and ("volces.com" in base or "bigmodel.cn" in base):
        payload["thinking"] = {"type": "disabled"}
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers=auth_headers(base, key),
            json=payload,
            timeout=httpx.Timeout(2.2, connect=2.0),
            trust_env=False,
        )
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
        text = message.get("content") if isinstance(message, dict) else ""
        if isinstance(text, list):
            text = "\n".join(str(item.get("text") or "") for item in text if isinstance(item, dict))
        found = parse_lines(str(text or ""))
    except Exception as exc:
        print(f"[tavern] line fallback ({type(exc).__name__})", flush=True)
        return None
    if not found:
        print("[tavern] line fallback (unparsed)", flush=True)
        return None
    print(f"[tavern] line {kind}", flush=True)
    return found
