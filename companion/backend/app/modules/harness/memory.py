"""Bounded, verbatim continuity notes from the host's confirmed chat history.

These are evidence excerpts, not inferred facts or a second model's personality.
The existing long-term memory module remains the source of recalled facts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Sequence

CONTEXT_BUDGET = 20000
_PREFERENCE = re.compile(r"喜欢|不喜欢|讨厌|偏好|以后.{0,12}(叫|用|别|不要)|记住|我叫|我的名字")
_COMMITMENT = re.compile(r"答应|约好|下次|明天|以后|等你|我会|我们.{0,8}(一起|再)")


def estimate_tokens(text: str) -> int:
    # Conservative for mixed Chinese, tags and English; avoids another tokenizer
    # dependency and leaves room for the runtime's system prompt and tool catalog.
    return (len((text or "").encode("utf-8")) + 1) // 2


def read_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def continuity(state: dict, prior: Sequence[dict] | None) -> str:
    buckets = {key: list(state.get(key) or []) for key in ("preferences", "commitments")}
    for message in prior or []:
        role = message.get("role")
        text = str(message.get("content") or "").strip()
        key = "preferences" if role == "user" else "commitments"
        pattern = _PREFERENCE if role == "user" else _COMMITMENT
        if role not in {"user", "assistant"} or not pattern.search(text):
            continue
        excerpt = text[:240]
        if excerpt not in buckets[key]:
            buckets[key].append(excerpt)
    for key, values in buckets.items():
        state[key] = values[-8:]
    parts = []
    for key, title in (("preferences", "对方曾表达的偏好"), ("commitments", "曾说过的约定或后续话题")):
        if state[key]:
            parts.append(title + "：\n" + "\n".join(state[key]))
    if not parts:
        return ""
    return ("【延续记忆】\n以下是已记录对话的原话摘录，可能已过时或已完成；"
            "以最新现场和对方这句为准，不把约定当成已发生的事实。\n" + "\n".join(parts))
