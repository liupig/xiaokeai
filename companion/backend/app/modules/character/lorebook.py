"""世界书引擎：关键词触发的动态上下文注入（对齐酒馆 Lorebook）。

每轮对话前扫用户输入 + 最近几轮历史，命中关键词的条目按 order 注入 prompt。
支持：普通关键词、/正则/i、常驻条目、选择性条目（secondary 也要命中）、
一轮递归（注入内容再触发别的条目）。注入总量封顶，超出的丢弃。
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List, Sequence

from .card import LorebookEntry

MAX_DEPTH = 2            # 递归扫描最多两轮，防止条目互相触发死循环
MAX_TOTAL_CHARS = 2400   # 一次注入的内容上限，超出按 order 丢弃
HISTORY_ROUNDS = 3       # 扫描最近几轮对话


@lru_cache(maxsize=2048)
def _compiled(pattern: str, flags: int) -> re.Pattern | None:
    """正则关键词编译缓存：大卡每轮都扫，不能每轮重编同一批表达式。"""
    try:
        return re.compile(pattern, flags)
    except re.error:
        return None


def _keyword_hit(keyword: str, text: str, case_sensitive: bool = False) -> bool:
    kw = (keyword or "").strip()
    if not kw:
        return False
    # /pattern/i 写法走正则（忽略大小写除非显式带 s 标记以外都按正则自身来）
    m = re.match(r"^/(.*)/([a-zA-Z]*)$", kw)
    if m:
        flags = 0 if ("s" in m.group(2) or case_sensitive) else re.IGNORECASE
        rx = _compiled(m.group(1), flags)
        return bool(rx and rx.search(text))
    if case_sensitive:
        return kw in text
    return kw.lower() in text.lower()


def _entry_hit(entry: LorebookEntry, text: str) -> bool:
    if not entry.keys:
        return False
    if not any(_keyword_hit(k, text, entry.case_sensitive) for k in entry.keys):
        return False
    if entry.selective and entry.selective_keys:
        return any(_keyword_hit(k, text, entry.case_sensitive) for k in entry.selective_keys)
    return True


def scan(
    entries: Sequence[LorebookEntry],
    user_text: str,
    history: Sequence[Dict[str, str]] | None = None,
    *,
    max_total_chars: int = MAX_TOTAL_CHARS,
    max_depth: int = MAX_DEPTH,
) -> List[str]:
    """返回按 order 排好序的命中内容。history 取最近几轮的文本一起扫。

    递归一轮：第一轮靠用户输入+历史触发；prevent_recursion 的条目只在第一轮
    有资格，exclude_recursion 的条目不参与第二轮的触发文本。
    """
    if not entries:
        return []
    recent = [str(m.get("content") or "") for m in (history or [])[-HISTORY_ROUNDS * 2:]]
    context = " ".join([user_text or ""] + recent)

    picked: List[LorebookEntry] = []
    seen: set[int] = set()
    scan_text = context
    for depth in range(max_depth):
        triggered = [
            e for e in entries
            if id(e) not in seen and e.enabled and not e.constant
            and not (depth > 0 and e.prevent_recursion)
            and _entry_hit(e, scan_text)
        ]
        constants = [e for e in entries if e.enabled and e.constant]
        batch = triggered + [e for e in constants if id(e) not in seen]
        if not batch:
            break
        batch.sort(key=lambda e: e.order)
        for e in batch:
            seen.add(id(e))
            picked.append(e)
        # 递归：拿刚注入的内容当新的扫描文本；exclude_recursion 的不算
        scan_text = " ".join(e.content for e in batch if not e.exclude_recursion)
        if not triggered:
            break

    picked.sort(key=lambda e: e.order)
    contents: List[str] = []
    total = 0
    for e in picked:
        body = (e.content or "").strip()
        if not body:
            continue
        if total + len(body) > max_total_chars:
            continue
        total += len(body)
        contents.append(body)
    return contents
