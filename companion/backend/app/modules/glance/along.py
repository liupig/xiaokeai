"""陪我看：对方说了才一直看。画面没变就不开口，变了才留一句给她接。"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from .service import eyes_glance
from .situation import Offer, situation

_START = ("陪我看", "陪着我看", "陪着看", "一直看着", "一直看我", "一起看")
_STOP = ("别看了", "不用看了", "不要看了", "先别看", "不用陪", "别陪", "停止陪看", "不要陪了", "别看屏幕")
_HOLD_UNTIL_SEED = 90
_AFTER_SEED = 12
_GAP = 8


@dataclass
class _State:
    on: bool = False
    character_id: int = 0
    seq: int = 0
    pending: str = ""
    last: str = ""
    trail: list[str] = field(default_factory=list)
    said: str = ""
    hold_until: float = 0
    user_until: float = 0
    offer: Offer | None = None


_lock = threading.Lock()
_state = _State()
_thread: threading.Thread | None = None


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def wants_stop(text: str) -> bool:
    compact = _compact(text)
    if not compact or len(compact) > 80:
        return False
    return any(word in compact for word in _STOP)


def wants_start(text: str) -> bool:
    compact = _compact(text)
    if not compact or len(compact) > 40 or wants_stop(text):
        return False
    return any(word in compact for word in _START)


def quiet_line(text: str) -> bool:
    compact = _compact(text).strip("。！!？?…")
    if not compact or len(compact) < 4:
        return True
    if compact.startswith("这一眼没看成"):
        return True
    if "没变" in compact and len(compact) <= 8:
        return True
    point = re.search(r"点[:：]\s*(.+)", text or "")
    if point:
        gist = re.split(r"劲[:：]", point.group(1), maxsplit=1)[0].strip("。！!？?… ")
        if gist in {"没得点", "没有", "无", "没变", "好看", "有趣", "不错", "好精彩", "加油", "在玩", "在看", "在听"}:
            return True
        if len(_compact(gist)) < 4:
            return True
    return compact in {"还是刚才那样", "还是一样", "没有变化", "没变化", "画面没变"}


def _grams(text: str) -> set[str]:
    kept = re.sub(r"[^\w\u4e00-\u9fff]+", "", text or "")
    if len(kept) < 2:
        return set()
    return {kept[i:i + 2] for i in range(len(kept) - 1)}


def same_scene(a: str, b: str) -> bool:
    left, right = _grams(a), _grams(b)
    if not left or not right:
        return False
    return len(left & right) / min(len(left), len(right)) >= 0.62


def snapshot() -> dict:
    with _lock:
        return {
            "on": _state.on,
            "seq": _state.seq,
            "text": _state.pending,
            "character_id": _state.character_id,
        }


def stop() -> None:
    with _lock:
        if not _state.on and not _state.pending:
            return
        _state.on = False
        _state.pending = ""
        _state.last = ""
        _state.trail.clear()
        _state.said = ""
        _state.user_until = 0
        _state.offer = None
    situation.reset()
    print("[along] stop")


def start(character_id: int) -> None:
    global _thread
    if not character_id:
        return
    with _lock:
        _state.on = True
        _state.character_id = int(character_id)
        _state.hold_until = time.time() + _HOLD_UNTIL_SEED
        _state.offer = None
        situation.reset()
        alive = _thread is not None and _thread.is_alive()
        if not alive:
            _thread = threading.Thread(target=_loop, name="glance-along", daemon=True)
            _thread.start()
    print(f"[along] start cid={character_id}")


def ack(seq: int) -> None:
    with _lock:
        if int(seq) == _state.seq:
            _state.pending = ""


def _remember(text: str) -> None:
    """调用时已拿着锁。留下最近几次真的变化，供下一眼和她接着说。"""
    item = " ".join((text or "").split())[:180]
    if not item:
        return
    if not _state.trail or _state.trail[-1] != item:
        _state.trail.append(item)
        del _state.trail[:-6]
    _state.last = item


def candidate_alive() -> bool:
    with _lock:
        offer = _state.offer
        if offer is None or time.time() < _state.user_until:
            return False
        return situation.still_valid(offer)


def open_candidate(text: str, prior: list | None = None) -> str | None:
    """开口前复查。失效就丢掉，不把过期的评论交给她。"""
    with _lock:
        offer = _state.offer
        pending = _state.pending
        if not _state.on or offer is None or (text or "").strip() != pending.strip():
            return None
        if time.time() < _state.user_until or not situation.still_valid(offer):
            _state.pending = ""
            _state.offer = None
            print("[along] drop stale")
            return None
        from .service import _spoken

        talked: list[str] = []
        for message in prior or []:
            role = (message.get("role") or "").strip()
            content = _spoken(message.get("content") or "")
            if role not in {"user", "assistant"} or not content:
                continue
            who = "她" if role == "assistant" else "对方"
            talked.append(f"{who}：{content}")
        lines = [situation.blocks()]
        if talked:
            lines.append("【刚说过】\n" + "\n".join(talked[-8:]))
        older = [line for line in _state.trail if line.strip() and line.strip() != pending.strip()]
        if older:
            lines.append("【画面经过】\n" + "\n".join(f"{i + 1}. {line}" for i, line in enumerate(older[-6:])))
        raw = situation.latest.raw if situation.latest is not None else pending
        lines.append("【眼前】" + raw)
        return "\n".join(lines)


def finish_speak(spoke: bool) -> None:
    situation.note_offered(spoke)
    if spoke:
        return
    with _lock:
        _state.pending = ""
        _state.offer = None


def eyes_context() -> str:
    """眼睛看下一眼时带上的经过，以及他刚说的那句。"""
    with _lock:
        trail = list(_state.trail)
        said = _state.said
    parts: list[str] = []
    if said:
        parts.append("他刚说：" + said)
    if trail:
        parts.append("画面经过：\n" + "\n".join(f"{i + 1}. {line}" for i, line in enumerate(trail)))
    return "\n".join(parts)[:700]


def trail_lines() -> list[str]:
    with _lock:
        return list(_state.trail)


def seed_seen(note: str) -> None:
    """开场那一眼已经说过。下一眼和它对上，同一件事就不再开口。"""
    raw = note or ""
    idx = raw.rfind("【眼前】")
    text = raw[idx + 4:].strip() if idx >= 0 else ""
    if not text or quiet_line(text):
        return
    with _lock:
        if not _state.on:
            return
        _remember(text)
        _state.hold_until = time.time() + _AFTER_SEED


def note_user(text: str, character_id: int, *, glance: bool, harness: bool) -> None:
    if not glance or not harness:
        stop()
        return
    if wants_stop(text):
        stop()
        return
    if wants_start(text):
        start(character_id)
    with _lock:
        if _state.on:
            # 用户的话走旁路。正在生成的主动陪看作废，不排队补说。
            _state.user_until = time.time() + 45
            _state.pending = ""
            _state.offer = None
            spoken = " ".join((text or "").split())
            if spoken:
                _state.said = spoken[:80]
                situation.note_user(spoken)


def release_user_turn() -> None:
    with _lock:
        _state.user_until = 0


def _modules_on() -> bool:
    try:
        from sqlmodel import Session

        from ...db import engine
        from ..flags import enabled as module_on

        with Session(engine) as session:
            return module_on(session, "glance") and module_on(session, "harness")
    except Exception:
        return False


def _tarot_now(character_id: int) -> bool:
    try:
        from ..tarot.service import active

        return bool(active(character_id))
    except Exception:
        return False


def _loop() -> None:
    while True:
        with _lock:
            if not _state.on:
                return
            character_id = _state.character_id
            pending = _state.pending
            hold = _state.hold_until
            user_until = _state.user_until
        if pending or time.time() < hold or time.time() < user_until:
            time.sleep(1)
            continue
        if not _modules_on():
            stop()
            return
        if _tarot_now(character_id):
            time.sleep(4)
            continue
        found = eyes_glance("", False, timeout=90, before=situation.eyes_before(), gate=True)
        text = str(found.get("text") or "").strip()
        if not found.get("ok") or found.get("skipped") or quiet_line(text):
            time.sleep(2 if found.get("skipped") else _GAP)
            continue
        from .situation import parse_observation

        obs = parse_observation(
            text,
            source=str(found.get("source") or "screen"),
            timestamp=found.get("observed_at"),
        )
        offer = situation.ingest(obs, allow_offer=True)
        if offer is None:
            time.sleep(_GAP)
            continue
        with _lock:
            if not _state.on or _state.pending or time.time() < _state.user_until:
                continue
            if not situation.still_valid(offer):
                print("[along] drop stale")
                continue
            _remember(offer.summary)
            _state.offer = offer
            _state.pending = offer.summary
            _state.seq += 1
            print(f"[along] seq={_state.seq} {offer.summary[:40]}")
        time.sleep(_GAP)
