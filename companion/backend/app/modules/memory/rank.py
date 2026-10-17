"""召回打分。钉住原句、事件、稳定事实分开，不碰向量库。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

VALID_KINDS = ("preference", "person", "event", "open_loop", "trait")
STABLE_KINDS = frozenset({"preference", "person", "trait"})
EVENT_KINDS = frozenset({"event", "open_loop"})
PEAK_EMOS = frozenset({"angry", "sad"})
CALM_EMOS = frozenset({"neutral", "relaxed", ""})

MAX_FACT_INJECT = 8
MAX_PINNED_FACTS = 3
EVENT_SLOTS = 4
MAX_MESSAGE_PINS = 4
MAX_PIN_CHARS = 400
VECTOR_FLOOR = 0.2
HALF_LIFE_DAYS = 3.0
W_RECENCY = 0.15
W_EMOTION = 0.15
W_IMPORTANCE = 0.1
DEFAULT_INTENSITY = 0.85
PEAK_INTENSITY = 0.95
EPISODE_OVERLAP = 0.12

_EMO_RE = re.compile(r"\[emo:([A-Za-z_]+)(?::([0-9]*\.?[0-9]+))?\]")
_RECALL_RE = re.compile(
    r"(记得|还记得|上次|那天|以前|约定|承诺|吵架|说过|remember|last time|promise)",
    re.I,
)
_ANGRY_RE = re.compile(r"(生气|吵架|大吵|摔门|发火|气得|愤怒|很气)")
_SAD_RE = re.compile(r"(伤心|难过|哭了|委屈|心碎)")
_BANTER_RE = re.compile(r"(随时喊|随时叫|随时找|想喝|奶茶|发呆|无聊|随便聊|热乎的)")
_LOOP_STOP = "用户助手答应约定此事尚未完成已经还没"
VECTOR_KEEP = 0.42
OVERLAP_KEEP = 0.12


def parse_emotion(text: str) -> tuple[str, float]:
    """读第一条 [emo:name] 或 [emo:name:0.4]。没写强度时用表演协议的缺省 0.85。"""
    match = _EMO_RE.search(text or "")
    if not match:
        return "", 0.0
    name = match.group(1).lower()
    raw = match.group(2)
    if raw is None or raw == "":
        intensity = DEFAULT_INTENSITY
    else:
        try:
            intensity = float(raw)
        except ValueError:
            intensity = DEFAULT_INTENSITY
    return name, max(0.0, min(1.0, intensity))


def emotion_from_words(text: str) -> tuple[str, float]:
    """对话里写了生气、吵架、摔门，就记成情绪峰值。不靠表演标签。"""
    blob = text or ""
    if _ANGRY_RE.search(blob):
        return "angry", 0.9
    if _SAD_RE.search(blob):
        return "sad", 0.85
    return "", 0.0


def emotion_peak(name: str, intensity: float) -> float:
    """只有生气、伤心，或强度明显高于缺省，才算峰值。放松和自然不加分。"""
    emo = (name or "").strip().lower()
    try:
        level = max(0.0, min(1.0, float(intensity or 0)))
    except (TypeError, ValueError):
        level = 0.0
    if not emo or emo in CALM_EMOS:
        return 0.0
    if emo in PEAK_EMOS:
        return level if level > 0 else DEFAULT_INTENSITY
    if level >= PEAK_INTENSITY:
        return level
    return 0.0


def recency_score(when: Optional[datetime], now: datetime, half_life_days: float = HALF_LIFE_DAYS) -> float:
    """1 是刚才，半衰期默认 3 天。没有时间就给中位，避免旧数据被当成刚刚发生。"""
    if when is None:
        return 0.5
    if when.tzinfo is not None:
        when = when.replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    age_days = max(0.0, (now - when).total_seconds() / 86400.0)
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)


def event_score(vector: float, recency: float, peak: float, importance: float) -> float:
    """三项都先收到 0–1，再相加。向量分不过门槛的句子不要拿来调用这个函数。"""
    vector = _unit(vector)
    recency = _unit(recency)
    peak = _unit(peak)
    importance = _unit(importance)
    return vector + W_RECENCY * recency + W_EMOTION * peak + W_IMPORTANCE * importance


def _unit(value: float) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, num))


def clamp_vector(score: float) -> float:
    try:
        num = float(score)
    except (TypeError, ValueError):
        return 0.0
    if num > 1.0 and num <= 100.0:
        num = num / 100.0
    return _unit(num)


def select_message_pins(
    pins: Sequence[Dict[str, Any]],
    *,
    limit: int = MAX_MESSAGE_PINS,
    char_budget: int = MAX_PIN_CHARS,
) -> List[Dict[str, Any]]:
    """留下最新的几条，总字数有上限，再按钉住的先后注入。"""
    ordered = sorted(
        pins,
        key=lambda row: (str(row.get("created_at") or ""), int(row.get("id") or 0)),
    )
    chosen: List[Dict[str, Any]] = []
    used = 0
    for row in reversed(ordered):
        text = (row.get("content") or "").strip()
        if not text:
            continue
        if len(chosen) >= limit:
            break
        if used + len(text) > char_budget:
            if chosen:
                break
            clipped = dict(row)
            clipped["content"] = text[:char_budget]
            chosen.append(clipped)
            break
        chosen.append(row)
        used += len(text)
    chosen.reverse()
    return chosen


def assemble_facts(
    pinned: Sequence[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
    stable: Sequence[Dict[str, Any]],
    *,
    limit: int = MAX_FACT_INJECT,
    pin_cap: int = MAX_PINNED_FACTS,
    event_slots: int = EVENT_SLOTS,
) -> List[Dict[str, Any]]:
    """姓名等事实置顶占固定名额；事件和偏好再分剩下的位子。"""
    seen = set()
    out: List[Dict[str, Any]] = []

    def take(rows: Sequence[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
        got: List[Dict[str, Any]] = []
        if count <= 0:
            return got
        for row in rows:
            rid = str(row.get("id") or "")
            text = (row.get("content") or "").strip()
            if not rid or not text or rid in seen:
                continue
            seen.add(rid)
            got.append(row)
            if len(got) >= count:
                break
        return got

    pins = take(pinned, pin_cap)
    remain = limit - len(pins)
    ev = take(events, min(event_slots, remain))
    remain = limit - len(pins) - len(ev)
    st = take(stable, remain)
    remain = limit - len(pins) - len(ev) - len(st)
    extra = take(events, remain)
    out.extend(pins)
    out.extend(ev)
    out.extend(extra)
    out.extend(st)
    return out[:limit]


def same_memory(left: str, right: str) -> bool:
    """两句说的是同一件事时，不要再存一条。"""
    a = (left or "").strip()
    b = (right or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    return max(query_overlap(a, b), query_overlap(b, a)) >= 0.72


def query_overlap(query: str, summary: str) -> float:
    """问句里有多少二字片段出现在摘要里。短问句也能擦到「吵架」。"""
    left = _grams(query)
    right = _grams(summary)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def recall_cue(query: str) -> bool:
    return bool(_RECALL_RE.search(query or ""))


def relevant_enough(vector: float, query: str, content: str) -> bool:
    """弱相关的闲聊不要把一堆私事塞进提示词。置顶事实不走这里。"""
    try:
        score = float(vector)
    except (TypeError, ValueError):
        score = 0.0
    if score >= VECTOR_KEEP:
        return True
    if score < VECTOR_FLOOR:
        return False
    return query_overlap(query, content) >= OVERLAP_KEEP


def allow_extracted(text: str, kind: str, user_blob: str = "") -> bool:
    """客套和助手随口提议不入库。未完约定必须能在用户原话里找到依据。"""
    if _BANTER_RE.search(text or ""):
        return False
    if kind != "open_loop" or not (user_blob or "").strip():
        return True
    grams = _grams(text) - _grams(_LOOP_STOP)
    if len(grams) < 2:
        return False
    hit = sum(1 for gram in grams if gram in user_blob)
    return hit >= 2 and hit / len(grams) >= 0.34


def pick_episode_row(
    episodes: Sequence[Dict[str, Any]],
    query: str,
    fact_ids: Optional[Sequence[Any]] = None,
    *,
    overlap_at: float = EPISODE_OVERLAP,
) -> Optional[Dict[str, Any]]:
    """摘要跟着已经召回的事实走。对不上事实时，再看问句是否擦到摘要。"""
    rows = [row for row in episodes if (row.get("summary") or "").strip()]
    if not rows or not (query or "").strip():
        return None
    wanted = set()
    for item in fact_ids or []:
        if str(item).isdigit():
            wanted.add(int(item))
    linked = []
    for row in rows:
        keys = {
            int(x) for x in (row.get("key_events") or [])
            if str(x).isdigit()
        }
        if wanted and keys & wanted:
            linked.append(row)
    if linked:
        return max(
            linked,
            key=lambda row: (
                query_overlap(query, row.get("summary") or ""),
                str(row.get("created_at") or ""),
            ),
        )
    ranked = sorted(rows, key=lambda row: str(row.get("created_at") or ""))
    best = max(ranked, key=lambda row: query_overlap(query, row.get("summary") or ""))
    best_score = query_overlap(query, best.get("summary") or "")
    if best_score >= overlap_at:
        return best
    if recall_cue(query):
        return ranked[-1]
    return None


def attach_source(window: Sequence[Dict[str, Any]], index: int) -> Dict[str, Any]:
    """序号从 1 开始。说话人和消息 id 从窗口来，不信模型抄的数据库 id。

    来源是用户时，情绪用同一轮里下一条助手回复的表演标签。
    """
    if index < 1 or index > len(window):
        return {"speaker": "", "source_message_id": 0, "emotion": "", "emotion_intensity": 0.0}
    src = window[index - 1]
    speaker = str(src.get("role") or "")
    try:
        mid = int(src.get("id") or 0)
    except (TypeError, ValueError):
        mid = 0
    if speaker == "assistant":
        return {
            "speaker": speaker,
            "source_message_id": mid,
            "emotion": str(src.get("emotion") or ""),
            "emotion_intensity": float(src.get("emotion_intensity") or 0),
        }
    for nxt in window[index:]:
        if str(nxt.get("role") or "") != "assistant":
            continue
        return {
            "speaker": speaker or "user",
            "source_message_id": mid,
            "emotion": str(nxt.get("emotion") or ""),
            "emotion_intensity": float(nxt.get("emotion_intensity") or 0),
        }
    return {
        "speaker": speaker or "user",
        "source_message_id": mid,
        "emotion": "",
        "emotion_intensity": 0.0,
    }


def importance_for(kind: str, peak: float, identity: bool) -> float:
    if identity:
        return 0.9
    if kind == "open_loop":
        return 0.7
    if peak >= 0.5:
        return 0.75
    if kind == "event":
        return 0.55
    return 0.5


def _grams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", (text or "").lower())
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i:i + 2] for i in range(len(compact) - 1)}
