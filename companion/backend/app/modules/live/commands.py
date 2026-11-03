"""弹幕里的短指令。只认舞台已经会做的动作，不另造一套动作库。"""
from __future__ import annotations

import re

# 短句才当指令。长评论仍交给她说话。
_MAX = 20

_ACTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("nod", ("点头", "点个头"), "嗯，我点头。"),
    ("shake", ("摇头",), "这个我摇头。"),
    ("heart", ("比心", "比个心"), "给你们比心。"),
    ("greet", ("挥手", "打个招呼"), "嗨，我挥一下。"),
    ("bow", ("鞠躬",), "鞠躬。"),
    ("stretch", ("顺一下头发", "理头发", "头发乱", "伸懒腰"), "头发乱的话，我顺一下。"),
    ("cute", ("卖萌",), "那我卖个萌。"),
    ("clap", ("鼓掌", "拍个手"), "鼓掌。"),
    ("shy", ("害羞",), "别看我，有点害羞。"),
    ("dance", ("跳个舞", "跳一段", "跳舞"), "我跳一段。"),
)

_ALLOWED = {act for act, _words, _line in _ACTS}
_SONG = re.compile(r"点歌[:：\s]*[《]?([^》\n]{1,20})")


def match_act(text: str) -> str:
    raw = (text or "").strip()
    if not raw or len(raw) > _MAX:
        return ""
    for act, words, _line in _ACTS:
        if any(word in raw for word in words):
            return act
    return ""


def act_line(act: str) -> str:
    for name, _words, line in _ACTS:
        if name == act:
            return line
    return ""


def allowed_act(act: str) -> str:
    name = (act or "").strip().lower()
    return name if name in _ALLOWED else ""


def match_song(text: str, titles: list[str]) -> str:
    matched = _SONG.search(text or "")
    if not matched or not titles:
        return ""
    want = matched.group(1).strip().strip("《》")
    if not want:
        return ""
    for title in titles:
        if want == title or want in title or title in want:
            return title
    return ""


def blocked(text: str, words: str) -> bool:
    raw = text or ""
    for word in str(words or "").splitlines():
        token = word.strip()
        if token and token in raw:
            return True
    return False
