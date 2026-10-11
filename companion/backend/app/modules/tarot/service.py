"""发牌机 + 仪式状态机。牌面由代码填槽，模型不许改。"""
from __future__ import annotations

import hashlib
import random
import re
import threading
import time
from typing import Any, Dict, List, Optional

from . import deck, plays, reader
from ...locale_pack import LangRe, current_reply

# 口头入口。正则在 locales/*/intents.json。
_DRAW_CELTIC_RE = LangRe("tarot.celtic")
_DRAW_CHOICE_RE = LangRe("tarot.choice")
_DRAW_BOND_RE = LangRe("tarot.bond")
_DRAW_WORK_RE = LangRe("tarot.work")
_DRAW_BODY_RE = LangRe("tarot.body")
_DRAW_YESNO_RE = LangRe("tarot.yesno")
_DRAW_ADVICE_RE = LangRe("tarot.advice")
_DRAW_THREE_RE = LangRe("tarot.three")
_DRAW_ONE_RE = LangRe("tarot.one")
_DRAW_ANY_RE = LangRe("tarot.any")
_HER_DRAW_RE = LangRe("tarot.her_draw")
_CUT_RE = LangRe("tarot.cut")
_SOFT_OK_RE = LangRe("tarot.soft_ok")
_THANKS_RE = LangRe("tarot.thanks")
_LINGER_DONE_RE = LangRe("tarot.linger")
_CLAR_RE = LangRe("tarot.clar")
_EXIT_RE = LangRe("tarot.exit")
_SYNTH_RE = LangRe("tarot.synth")
_ASK_RE = LangRe("tarot.ask")
_REDEAL_RE = LangRe("tarot.redeal")
_STOP_RE = LangRe("tarot.stop")
_FLIP_RE = LangRe("tarot.flip")
_FAN_LEFT_RE = LangRe("tarot.fan_left")
_FAN_RIGHT_RE = LangRe("tarot.fan_right")
_FAN_MID_RE = LangRe("tarot.fan_mid")
_CN_ORD = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_lock = threading.RLock()
_sessions: Dict[int, Dict[str, Any]] = {}
_just_exited: Dict[int, bool] = {}


def _rng_of(seed: int) -> random.Random:
    return random.Random(seed & 0xFFFFFFFF)


def _mix_seed(seed: int, extra: str) -> int:
    h = hashlib.sha256(f"{seed}:{extra}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _empty_session() -> Dict[str, Any]:
    return {
        "active": False,
        "spread": "",
        "title": "",
        "layout": "row",
        "question": "",
        "phase": "off",
        "cards": [],
        "fan": [],
        "picked": [],
        "revealed": [],
        "focus": None,
        "dealt_at": 0.0,
        "last_text": "",
        "disclaimer": True,
        "step": 0,
        "need": 0,
        "can_continue": False,
        "can_cut": False,
        "can_pick": False,
        "can_her_draw": False,
        "can_clarifier": False,
        "hint": "",
        "clarifier_used": False,
        "done": False,
        "want_synth": False,
        "last_action": "",
        "wait": None,
        "can_pick_play": False,
        "plays": [],
    }


def _hint(st: Dict[str, Any]) -> str:
    from ...locale_pack import current_reply
    if current_reply() != "zh-CN":
        return _hint_i18n(st)
    phase = st.get("phase") or ""
    if phase == "intent":
        return "说第几个或玩法名，也可以点；「随便」默认时间线"
    play = plays.get_play(str(st.get("spread") or "daily"))
    n = int(play["n"])
    picked = len(st.get("picked") or [])
    pos = list(play["positions"])
    if phase == "shuffle":
        return f"她在洗「{play['title']}」"
    if phase == "cut":
        return "点一次切牌"
    if phase == "pick":
        slot = pos[picked] if picked < n else ""
        return f"点牌背 · 第 {picked + 1}/{n} 张" + (f"「{slot}」" if slot else "")
    if phase in ("placed", "open"):
        left = n - len(st.get("revealed") or [])
        if left > 0:
            return f"说「翻转」或点牌 · 还剩 {left} 张，语音约 10 秒后自动翻"
        return "可以收线了"
    if phase == "synth":
        return "她在收线"
    if phase == "linger":
        if not st.get("clarifier_used"):
            return "点一张追问，或说「再翻一张补」「收起来」"
        return "点一张追问，或者说「收起来」"
    return ""


def _hint_i18n(st: Dict[str, Any]) -> str:
    from ...locale_pack import current_reply
    lang = current_reply()
    ja = lang == "ja"
    ko = lang == "ko"
    phase = st.get("phase") or ""
    if phase == "intent":
        if ja:
            return "番号か遊び方を言って。タップでもいい"
        if ko:
            return "번호나 놀이 방식을 말해. 눌러도 돼"
        return "Say a number or a spread, or tap one"
    play = plays.get_play(str(st.get("spread") or "daily"))
    n = int(play["n"])
    picked = len(st.get("picked") or [])
    pos = plays.spread_positions(play)
    title = plays.spread_title(play)
    if phase == "shuffle":
        if ja:
            return f"「{title}」を切ってる"
        if ko:
            return f"「{title}」 섞는 중"
        return f"Shuffling {title}"
    if phase == "cut":
        if ja:
            return "一度切って"
        if ko:
            return "한 번 잘라"
        return "Cut once"
    if phase == "pick":
        slot = pos[picked] if picked < n else ""
        base = f"{picked + 1}/{n}"
        if ja:
            return f"裏をタップ · {base}" + (f"「{slot}」" if slot else "")
        if ko:
            return f"뒷면을 눌러 · {base}" + (f"「{slot}」" if slot else "")
        return f"Tap a card back · {base}" + (f" · {slot}" if slot else "")
    if phase in ("placed", "open"):
        left = n - len(st.get("revealed") or [])
        if left > 0:
            if ja:
                return f"「めくって」かタップ · 残り {left}"
            if ko:
                return f"「뒤집어」 또는 눌러 · 남은 {left}"
            return f"Say flip, or tap · {left} left"
        if ja:
            return "まとめていい"
        if ko:
            return "이제 모아도 돼"
        return "Ready to close"
    if phase == "synth":
        if ja:
            return "まとめている"
        if ko:
            return "모으는 중"
        return "Closing the reading"
    if phase == "linger":
        if not st.get("clarifier_used"):
            if ja:
                return "一枚聞いて、または「もう一枚」「しまって」"
            if ko:
                return "한 장 묻거나, 「한 장 더」「집어넣어」"
            return "Ask one card, or say another card, or put them away"
        if ja:
            return "一枚聞くか、「しまって」"
        if ko:
            return "한 장 묻거나 「집어넣어」"
        return "Ask one card, or put them away"
    return ""


def snapshot(character_id: int) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return _empty_session()
        phase = str(st.get("phase") or "")
        if phase == "intent":
            return {
                "active": True,
                "spread": "",
                "title": (
                    "选玩法" if current_reply() == "zh-CN"
                    else "遊び方" if current_reply() == "ja"
                    else "놀이" if current_reply() == "ko"
                    else "Choose a spread"
                ),
                "layout": "row",
                "question": st.get("question") or "",
                "phase": "intent",
                "cards": [],
                "fan": [],
                "picked": [],
                "revealed": [],
                "focus": None,
                "dealt_at": st.get("dealt_at") or 0.0,
                "last_text": st.get("last_text") or "",
                "disclaimer": False,
                "step": 0,
                "need": 0,
                "can_continue": False,
                "can_cut": False,
                "can_pick": False,
                "can_her_draw": False,
                "can_clarifier": False,
                "hint": _hint(st),
                "clarifier_used": False,
                "done": False,
                "want_synth": False,
                "all_revealed": False,
                "last_action": st.get("last_action") or "offer",
                "wait": None,
                "can_pick_play": True,
                "plays": plays.list_plays(),
            }
        play = plays.get_play(str(st.get("spread") or "daily"))
        n = int(play["n"])
        revealed = list(st.get("revealed") or [])
        phase = str(st.get("phase") or "")
        all_up = len(revealed) >= n and n > 0
        linger = phase == "linger"
        return {
            "active": True,
            "spread": play["id"],
            "title": plays.spread_title(play),
            "layout": play["layout"],
            "question": st.get("question") or "",
            "phase": phase,
            "cards": list(st.get("cards") or []),
            "fan": list(st.get("fan") or []),
            "picked": list(st.get("picked") or []),
            "revealed": revealed,
            "focus": st.get("focus"),
            "dealt_at": st.get("dealt_at") or 0.0,
            "last_text": st.get("last_text") or "",
            "disclaimer": False,
            "step": int(st.get("step") or 0),
            "need": n,
            "can_continue": bool(st.get("want_synth")) and not st.get("done"),
            "can_cut": phase == "cut",
            "can_pick": phase == "pick",
            "can_her_draw": phase == "pick",
            "can_clarifier": linger and not st.get("clarifier_used") and bool(st.get("cards")),
            "hint": _hint(st),
            "clarifier_used": bool(st.get("clarifier_used")),
            "done": bool(st.get("done")),
            "want_synth": bool(st.get("want_synth")),
            "all_revealed": all_up,
            "last_action": st.get("last_action") or "",
            "wait": _wait_of(st),
            "can_pick_play": False,
            "plays": [],
        }


_WAIT_CUT_SEC = 12
_WAIT_DRAW_SEC = 12
_WAIT_REVEAL_SEC = 10
_last_progress: Dict[int, Dict[str, Any]] = {}


def _wait_of(st: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """当前相位前端该等什么：切牌 / 代抽 / 翻面。sec 给语音局自动推进。"""
    if not st:
        return None
    phase = str(st.get("phase") or "")
    play = plays.get_play(str(st.get("spread") or "daily"))
    n = int(play["n"])
    revealed = len(st.get("revealed") or [])
    if phase in ("shuffle", "cut"):
        return {"next": "cut", "sec": _WAIT_CUT_SEC}
    if phase == "pick":
        return {"next": "her_draw", "sec": _WAIT_DRAW_SEC}
    if phase in ("placed", "open") and revealed < n:
        return {"next": "reveal", "sec": _WAIT_REVEAL_SEC}
    return None


def _stash_progress(character_id: int, action: str) -> None:
    with _lock:
        st = _sessions.get(character_id)
        if action == "dismiss":
            snap = _empty_session()
            snap["exited"] = True
            _last_progress[character_id] = {
                "type": "tarot",
                "action": "dismiss",
                "wait": None,
                "session": snap,
            }
            return
        if not st:
            return
        if action not in ("keep", "none"):
            st["last_action"] = action
        elif not st.get("last_action"):
            st["last_action"] = action
    snap = snapshot(character_id)
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return
        _last_progress[character_id] = {
            "type": "tarot",
            "action": str(st.get("last_action") or action or "keep"),
            "wait": snap.get("wait"),
            "session": snap,
        }


def progress_event(character_id: int, *, consume_exit: bool = False) -> Optional[Dict[str, Any]]:
    """给 chat SSE 用的结构化进度。模型不驱动状态机，前端跟这份走。"""
    with _lock:
        playing = character_id in _sessions
        cached = _last_progress.get(character_id)
    if playing:
        snap = snapshot(character_id)
        with _lock:
            st = _sessions.get(character_id)
            action = str(
                (st or {}).get("last_action")
                or (cached or {}).get("action")
                or "keep"
            )
        out = {
            "type": "tarot",
            "action": action,
            "wait": snap.get("wait"),
            "session": snap,
        }
        with _lock:
            _last_progress[character_id] = out
        return out
    if cached and cached.get("action") == "dismiss":
        if consume_exit:
            with _lock:
                _last_progress.pop(character_id, None)
        return cached
    return None


def isolate_prompt(character_id: int, mode: str, text: str = "") -> bool:
    mode_l = (mode or "user").lower()
    if mode_l not in ("user", "continue"):
        return False
    t = (text or "").strip()
    if _is_exit(t) or _STOP_RE.search(t):
        return False
    if active(character_id):
        return True
    return mode_l == "user" and _is_draw(t)


def can_continue(character_id: int) -> bool:
    return bool(snapshot(character_id).get("can_continue"))


def active(character_id: int) -> bool:
    with _lock:
        return character_id in _sessions


def should_speak(character_id: int) -> bool:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return False
        if st.get("done") and not st.get("want_synth"):
            return False
        return True


def clear(character_id: int, *, exited: bool = False) -> None:
    with _lock:
        _sessions.pop(character_id, None)
        if exited:
            _just_exited[character_id] = True
            snap = _empty_session()
            snap["exited"] = True
            _last_progress[character_id] = {
                "type": "tarot",
                "action": "dismiss",
                "wait": None,
                "session": snap,
            }
        else:
            _just_exited.pop(character_id, None)
            _last_progress.pop(character_id, None)


def _orient(card: Dict[str, object], reversed: bool) -> Dict[str, Any]:
    item = deck.enrich(card)
    hint = str(item["hint_rev"] if reversed else item["hint_up"])
    return {
        "id": item["id"],
        "name": deck.display_name(item, current_reply()),
        "file": item["file"],
        "url": item["url"],
        "has_art": item["has_art"],
        "arcana": item["arcana"],
        "suit": item["suit"],
        "reversed": reversed,
        "hint": deck.display_hint(item, reversed, current_reply()) if current_reply() != "zh-CN" else hint,
        "back_url": item["back_url"],
        "back_ready": item["back_ready"],
        "clarifier": False,
    }


def normalize_spread(spread: str) -> str:
    return plays.normalize_spread(spread)


def _build_fan(seed: int, spread: str) -> List[Dict[str, Any]]:
    rng = _rng_of(seed)
    pool = list(deck.list_cards())
    rng.shuffle(pool)
    n = plays.fan_size(spread)
    out = []
    for i, raw in enumerate(pool[:n]):
        row = _orient(raw, rng.random() < 0.5)
        row["fan_index"] = i
        out.append(row)
    return out


def begin(character_id: int, spread: str, question: str = "", *, redeal: bool = False) -> Dict[str, Any]:
    spread = normalize_spread(spread)
    play = plays.get_play(spread)
    now = time.time()
    seed = int(now * 1000) ^ (character_id * 7919)
    with _lock:
        first = character_id not in _sessions
        if character_id in _sessions and not redeal:
            return snapshot(character_id)
        _sessions[character_id] = {
            "spread": spread,
            "question": (question or "").strip()[:80],
            "phase": "shuffle",
            "seed": seed,
            "fan": _build_fan(seed, spread),
            "picked": [],
            "cards": [],
            "revealed": [],
            "focus": None,
            "step": 0,
            "done": False,
            "want_synth": False,
            "clarifier_used": False,
            "dealt_at": now,
            "last_text": "",
            "last_action": "draw",
        }
        _just_exited.pop(character_id, None)
    snap = snapshot(character_id)
    snap["disclaimer"] = first
    snap["action"] = "begin"
    return snap


def offer(character_id: int, question: str = "") -> Dict[str, Any]:
    """语音/口头「看牌」还没点名玩法：先问选哪一套。"""
    now = time.time()
    q = (question or "").strip()[:80]
    with _lock:
        st = _sessions.get(character_id)
        if st and str(st.get("phase") or "") == "intent":
            if q:
                st["question"] = q
            st["last_action"] = "offer"
            st["last_text"] = q or st.get("last_text") or ""
            return snapshot(character_id)
        _sessions[character_id] = {
            "spread": "",
            "question": q,
            "phase": "intent",
            "seed": int(now * 1000) ^ (character_id * 7919),
            "fan": [],
            "picked": [],
            "cards": [],
            "revealed": [],
            "focus": None,
            "step": 0,
            "done": False,
            "want_synth": False,
            "clarifier_used": False,
            "dealt_at": now,
            "last_text": q,
            "last_action": "offer",
        }
        _just_exited.pop(character_id, None)
    snap = snapshot(character_id)
    snap["disclaimer"] = True
    snap["action"] = "offer"
    return snap


def ready_cut(character_id: int) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return _empty_session()
        if st.get("phase") == "shuffle":
            st["phase"] = "cut"
    return snapshot(character_id)


def cut(character_id: int, entropy: str = "") -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return _empty_session()
        if st.get("phase") not in ("shuffle", "cut"):
            return snapshot(character_id)
        extra = entropy or str(time.time())
        st["seed"] = _mix_seed(int(st.get("seed") or 1), extra)
        st["fan"] = _build_fan(int(st["seed"]), str(st["spread"]))
        st["picked"] = []
        st["cards"] = []
        st["revealed"] = []
        st["phase"] = "pick"
        st["last_text"] = "切牌"
        st["last_action"] = "cut"
    return snapshot(character_id)


def _place_locked(st: Dict[str, Any]) -> None:
    play = plays.get_play(str(st["spread"]))
    positions = plays.spread_positions(play)
    n = int(play["n"])
    fan: List[Dict[str, Any]] = list(st.get("fan") or [])
    picked: List[int] = list(st.get("picked") or [])
    cards = []
    for i, fi in enumerate(picked[:n]):
        if fi < 0 or fi >= len(fan):
            continue
        row = dict(fan[fi])
        row["position"] = positions[i] if i < len(positions) else f"第{i + 1}"
        row["index"] = i
        row.pop("fan_index", None)
        cards.append(row)
    st["cards"] = cards
    st["revealed"] = []
    st["phase"] = "placed"
    st["focus"] = None
    st["step"] = 0
    st["want_synth"] = False
    st["done"] = False


def pick(character_id: int, fan_index: int) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st or st.get("phase") != "pick":
            return snapshot(character_id) if st else _empty_session()
        play = plays.get_play(str(st["spread"]))
        n = int(play["n"])
        fan = st.get("fan") or []
        fi = int(fan_index)
        if fi < 0 or fi >= len(fan):
            return snapshot(character_id)
        picked: List[int] = list(st.get("picked") or [])
        if fi in picked:
            return snapshot(character_id)
        if len(picked) >= n:
            return snapshot(character_id)
        picked.append(fi)
        st["picked"] = picked
        st["last_text"] = f"点选第{len(picked)}张"
        if len(picked) >= n:
            _place_locked(st)
            st["last_action"] = "place"
        else:
            st["last_action"] = "pick"
    return snapshot(character_id)


def her_draw(character_id: int) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st or st.get("phase") != "pick":
            return snapshot(character_id) if st else _empty_session()
        play = plays.get_play(str(st["spread"]))
        n = int(play["n"])
        fan = st.get("fan") or []
        picked: List[int] = list(st.get("picked") or [])
        left = [i for i in range(len(fan)) if i not in picked]
        rng = _rng_of(int(st.get("seed") or 1) ^ 17)
        rng.shuffle(left)
        need = n - len(picked)
        picked.extend(left[:need])
        st["picked"] = picked[:n]
        st["last_text"] = "你来抽"
        st["last_action"] = "place"
        _place_locked(st)
    return snapshot(character_id)


def reveal(character_id: int, index: int) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return _empty_session()
        if st.get("phase") not in ("placed", "open", "linger"):
            return snapshot(character_id)
        cards = st.get("cards") or []
        i = int(index)
        if i < 0 or i >= len(cards):
            return snapshot(character_id)
        revealed: List[int] = list(st.get("revealed") or [])
        if i not in revealed:
            revealed.append(i)
            st["revealed"] = revealed
        st["focus"] = i
        st["step"] = i
        st["last_text"] = f"翻开第{i + 1}张"
        st["last_action"] = "reveal"
        play = plays.get_play(str(st["spread"]))
        n = int(play["n"])
        if st.get("phase") in ("placed", "open"):
            st["phase"] = "open"
            if len(revealed) >= n:
                st["want_synth"] = n > 1
                if n <= 1:
                    st["done"] = False
        elif st.get("phase") == "linger":
            st["done"] = False
    return snapshot(character_id)


def enter_linger(character_id: int, *, as_synth: bool = False) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return _empty_session()
        st["want_synth"] = False
        st["done"] = True
        st["phase"] = "linger"
        st["focus"] = None
        if as_synth:
            st["last_text"] = "综合"
    return snapshot(character_id)


def mark_synth_done(character_id: int) -> Dict[str, Any]:
    return enter_linger(character_id, as_synth=True)


def seal_linger(character_id: int) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return _empty_session()
        if st.get("phase") == "linger":
            st["done"] = True
            st["want_synth"] = False
    return snapshot(character_id)


def clarifier(character_id: int, host: Optional[int] = None) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st or st.get("clarifier_used"):
            return snapshot(character_id) if st else _empty_session()
        if st.get("phase") not in ("linger", "open"):
            return snapshot(character_id)
        used = {c.get("id") for c in (st.get("cards") or [])}
        rng = _rng_of(int(st.get("seed") or 1) ^ 99)
        pool = [c for c in deck.list_cards() if c.get("id") not in used]
        if not pool:
            return snapshot(character_id)
        rng.shuffle(pool)
        host_i = host if isinstance(host, int) else st.get("focus")
        cards: List[Dict[str, Any]] = list(st.get("cards") or [])
        pos = "补"
        if isinstance(host_i, int) and 0 <= host_i < len(cards):
            pos = f"{cards[host_i].get('position')}·补"
        row = _orient(pool[0], rng.random() < 0.5)
        row["position"] = pos
        row["index"] = len(cards)
        row["clarifier"] = True
        cards.append(row)
        st["cards"] = cards
        revealed = list(st.get("revealed") or [])
        revealed.append(row["index"])
        st["revealed"] = revealed
        st["focus"] = row["index"]
        st["clarifier_used"] = True
        st["phase"] = "linger"
        st["last_text"] = "再翻一张补"
        st["last_action"] = "clarifier"
    return snapshot(character_id)


def deal(character_id: int, spread: str, question: str = "") -> Dict[str, Any]:
    """兼容旧入口：开仪式并代抽，牌背面落入牌位，等点翻。"""
    begin(character_id, spread, question, redeal=True)
    cut(character_id, "auto")
    return her_draw(character_id)


def set_question(character_id: int, question: str) -> None:
    q = (question or "").strip()[:80]
    if not q:
        return
    with _lock:
        st = _sessions.get(character_id)
        if st:
            st["question"] = q


def set_focus(character_id: int, index: Optional[int]) -> Dict[str, Any]:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return _empty_session()
        cards = st.get("cards") or []
        if index is None or index < 0 or index >= len(cards):
            st["focus"] = None
        else:
            st["focus"] = int(index)
    return snapshot(character_id)


def _guess_spread(text: str) -> str:
    hit = plays.match_play_id(text)
    if hit:
        return hit
    if _DRAW_CELTIC_RE.search(text):
        return "celtic"
    if _DRAW_CHOICE_RE.search(text):
        return "choice"
    if _DRAW_BOND_RE.search(text):
        return "bond"
    if _DRAW_WORK_RE.search(text):
        return "work"
    if _DRAW_BODY_RE.search(text):
        return "body"
    if _DRAW_YESNO_RE.search(text):
        return "yesno"
    if _DRAW_ADVICE_RE.search(text):
        return "advice"
    if _DRAW_THREE_RE.search(text):
        return "three"
    return "daily"


def _is_vague_open(text: str) -> bool:
    """「看牌 / 玩塔罗」还没点名玩法。"""
    if plays.match_play_id(text):
        return False
    if (
        _DRAW_THREE_RE.search(text) or _DRAW_ADVICE_RE.search(text) or _DRAW_ONE_RE.search(text)
        or _DRAW_YESNO_RE.search(text) or _DRAW_BODY_RE.search(text) or _DRAW_BOND_RE.search(text)
        or _DRAW_WORK_RE.search(text) or _DRAW_CHOICE_RE.search(text) or _DRAW_CELTIC_RE.search(text)
    ):
        return False
    return bool(_DRAW_ANY_RE.search(text))


def _compact(text: str) -> str:
    return plays._compact(text)


def _wants_cut(text: str, phase: str) -> bool:
    if phase not in ("shuffle", "cut"):
        return False
    t = (text or "").strip()
    n = _compact(t)
    if not t:
        return False
    if _CUT_RE.search(t) or _CUT_RE.search(n) or n == "切":
        return True
    if _SOFT_OK_RE.search(n) or _STOP_RE.search(t) or n == "停":
        return True
    return False


def _wants_exit(text: str, phase: str, active: bool) -> bool:
    t = (text or "").strip()
    n = _compact(t)
    if not t:
        return False
    if t in ("算了", "算啦", "算了吧") or n in ("算了", "算啦", "算了吧"):
        return False
    if _is_exit(t) or _is_exit(n):
        return True
    if phase in ("shuffle", "cut") and _wants_cut(t, phase):
        return False
    if phase in ("linger", "synth"):
        if _THANKS_RE.search(t) or _SOFT_OK_RE.search(n) or _STOP_RE.search(t) or _LINGER_DONE_RE.search(n):
            return True
    if active and phase not in ("shuffle", "cut", "linger", "synth") and _STOP_RE.search(t):
        # 讲牌中途「停下」只掐话，不收摊；明确带收/不看才退。
        if re.search(r"不看|收|结束|关掉", n):
            return True
        return False
    return False


def _extract_question(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    for rx in (
        _DRAW_CELTIC_RE, _DRAW_CHOICE_RE, _DRAW_BOND_RE, _DRAW_WORK_RE,
        _DRAW_BODY_RE, _DRAW_YESNO_RE, _DRAW_ADVICE_RE, _DRAW_THREE_RE,
        _DRAW_ONE_RE, _DRAW_ANY_RE, _REDEAL_RE, _HER_DRAW_RE, _CUT_RE,
    ):
        t = rx.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" ，。,、.!！？?…")
    if len(t) < 2:
        return ""
    return t[:80]


def _is_exit(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t in ("算了", "算啦", "算了吧"):
        return False
    return bool(_EXIT_RE.search(t))


def _is_draw(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if plays.match_play_id(t):
        return True
    return bool(
        _DRAW_THREE_RE.search(t) or _DRAW_ADVICE_RE.search(t) or _DRAW_ONE_RE.search(t)
        or _DRAW_ANY_RE.search(t) or _DRAW_YESNO_RE.search(t) or _DRAW_BODY_RE.search(t)
        or _DRAW_BOND_RE.search(t) or _DRAW_WORK_RE.search(t) or _DRAW_CHOICE_RE.search(t)
        or _DRAW_CELTIC_RE.search(t)
    )


_EN_ORD = {
    "first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4,
    "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9,
    "1st": 0, "2nd": 1, "3rd": 2,
}


def _ordinal_to_index(raw: str) -> Optional[int]:
    if raw in _CN_ORD:
        return _CN_ORD[raw] - 1
    if raw.isdigit():
        return int(raw) - 1
    low = (raw or "").strip().lower()
    if low in _EN_ORD:
        return _EN_ORD[low]
    return None


def _named_card_index(st: Dict[str, Any], text: str) -> Optional[int]:
    t = (text or "").strip()
    cards: List[Dict[str, Any]] = list(st.get("cards") or [])
    if not t or not cards:
        return None
    labels = sorted({str(c.get("position") or "") for c in cards}, key=len, reverse=True)
    for label in labels:
        if label and label in t:
            for i, c in enumerate(cards):
                if c.get("position") == label:
                    return i
    m = re.search(r"第\s*([一二三四五六七八九十0-9]+)\s*张?", t)
    if not m and current_reply() != "zh-CN":
        m = re.search(
            r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|\d+)\b",
            t, re.IGNORECASE,
        )
    if not m:
        return None
    idx = _ordinal_to_index(m.group(1))
    if idx is not None and 0 <= idx < len(cards):
        return idx
    return None


def _maybe_focus(st: Dict[str, Any], text: str) -> None:
    idx = _named_card_index(st, text)
    if idx is not None:
        st["focus"] = idx


def _fan_choice(st: Dict[str, Any], text: str) -> Optional[int]:
    t = (text or "").strip()
    fan = list(st.get("fan") or [])
    picked = set(st.get("picked") or [])
    left = [i for i in range(len(fan)) if i not in picked]
    if not left:
        return None
    if _FAN_LEFT_RE.search(t):
        return left[0]
    if _FAN_RIGHT_RE.search(t):
        return left[-1]
    if _FAN_MID_RE.search(t):
        return left[len(left) // 2]
    m = re.search(r"第\s*([一二三四五六七八九十0-9]+)\s*张?", t)
    if m:
        raw = m.group(1)
        cmap = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        n = cmap.get(raw)
        if n is None and raw.isdigit():
            n = int(raw)
        if n is not None and 1 <= n <= len(fan) and (n - 1) not in picked:
            return n - 1
    return None


def _reveal_choice(st: Dict[str, Any], text: str) -> Optional[int]:
    t = (text or "").strip()
    cards: List[Dict[str, Any]] = list(st.get("cards") or [])
    revealed = set(int(x) for x in (st.get("revealed") or []))
    if not cards:
        return None
    named = _named_card_index(st, t)
    if named is not None:
        return named if named not in revealed else None
    if _FLIP_RE.search(t) or "翻" in t or _ASK_RE.search(t):
        for i in range(len(cards)):
            if i not in revealed:
                return i
    return None


def apply_user_text(character_id: int, mode: str, text: str) -> str:
    action = _digest_user_text(character_id, mode, text)
    _stash_progress(character_id, action)
    return action


def _digest_user_text(character_id: int, mode: str, text: str) -> str:
    mode_l = (mode or "user").lower()
    if mode_l == "continue":
        if not active(character_id):
            return "none"
        with _lock:
            st = _sessions.get(character_id)
            if st and st.get("want_synth") and not st.get("done"):
                st["phase"] = "synth"
                st["focus"] = None
                st["last_text"] = "综合"
        return "keep"
    if mode_l == "proactive":
        return "keep" if active(character_id) else "none"
    if mode_l != "user":
        return "keep" if active(character_id) else "none"
    t = (text or "").strip()
    if not t:
        return "keep" if active(character_id) else "none"

    phase = ""
    playing = False
    with _lock:
        st0 = _sessions.get(character_id)
        if st0:
            playing = True
            phase = str(st0.get("phase") or "")

    if playing:
        with _lock:
            st0 = _sessions.get(character_id)
            if st0 and str(st0.get("applied_text") or "") == t:
                age = time.time() - float(st0.get("applied_at") or 0)
                if age < 2.5:
                    return str(st0.get("last_action") or "keep")
            if st0:
                st0["applied_text"] = t
                st0["applied_at"] = time.time()

    if _wants_exit(t, phase, playing):
        if playing:
            clear(character_id, exited=True)
            return "dismiss"
        return "none"

    if playing and phase == "intent":
        hit = plays.resolve_play_choice(t)
        q = ""
        with _lock:
            st = _sessions.get(character_id)
            q = str((st or {}).get("question") or "")
        extra_q = _extract_question(t)
        if hit:
            begin(character_id, hit, extra_q or q, redeal=True)
            with _lock:
                st = _sessions.get(character_id)
                if st:
                    st["last_text"] = t
            return "draw"
        if extra_q:
            with _lock:
                st = _sessions.get(character_id)
                if st:
                    st["question"] = extra_q
                    st["last_text"] = t
                    st["last_action"] = "offer"
            return "keep"
        with _lock:
            st = _sessions.get(character_id)
            if st:
                st["last_text"] = t
        return "keep"

    if playing and _wants_cut(t, phase):
        cut(character_id, t)
        return "cut"

    if playing and (_HER_DRAW_RE.search(t) or _compact(t) in ("随便", "抽吧", "给我选", "选牌")):
        snap = her_draw(character_id)
        if snap.get("phase") == "placed":
            return "place"
        return "keep"

    if active(character_id):
        with _lock:
            st = _sessions.get(character_id)
            phase = str((st or {}).get("phase") or "")
        if phase == "pick":
            with _lock:
                st = _sessions.get(character_id)
                idx = _fan_choice(st, t) if st else None
            if idx is not None:
                snap = pick(character_id, idx)
                if snap.get("phase") == "placed":
                    return "place"
                return "pick"
        if phase in ("placed", "open") and (
            _FLIP_RE.search(t) or "翻" in t or _ASK_RE.search(t)
            or _named_card_index(st or {}, t) is not None
        ):
            with _lock:
                st = _sessions.get(character_id)
                idx = _reveal_choice(st, t) if st else None
                named = _named_card_index(st, t) if st else None
            if idx is not None:
                reveal(character_id, idx)
                return "reveal"
            if named is not None:
                with _lock:
                    st = _sessions.get(character_id)
                    if st:
                        st["focus"] = named
                        st["last_text"] = t
                return "keep"

    if active(character_id) and _CLAR_RE.search(t):
        clarifier(character_id)
        return "clarifier"

    if active(character_id) and _SYNTH_RE.search(t):
        with _lock:
            st = _sessions.get(character_id)
            if st:
                play = plays.get_play(str(st["spread"]))
                n = int(play["n"])
                if len(st.get("revealed") or []) >= n:
                    st["want_synth"] = True
                    st["done"] = False
                    st["phase"] = "synth"
                    st["last_text"] = t
        return "keep"

    if _is_draw(t) or (playing and _REDEAL_RE.search(t)):
        redeal = active(character_id) and bool(_REDEAL_RE.search(t))
        if active(character_id) and not redeal:
            with _lock:
                st = _sessions.get(character_id)
                if st:
                    st["last_text"] = t
                    q = _extract_question(t)
                    if q:
                        st["question"] = q
            return "keep"
        q = _extract_question(t)
        if (not redeal) and _is_vague_open(t):
            offer(character_id, q)
            with _lock:
                st = _sessions.get(character_id)
                if st:
                    st["last_text"] = t
            return "offer"
        spread = _guess_spread(t)
        if redeal and active(character_id):
            with _lock:
                st = _sessions.get(character_id)
                cur = str((st or {}).get("spread") or "")
            if cur:
                spread = cur
        begin(character_id, spread, q, redeal=True)
        with _lock:
            st = _sessions.get(character_id)
            if st:
                st["last_text"] = t
        return "draw"

    if not active(character_id):
        return "none"

    with _lock:
        st = _sessions.get(character_id)
        if st:
            st["last_text"] = t
            _maybe_focus(st, t)
            if st.get("phase") == "open" and _ASK_RE.search(t) and st.get("focus") is None:
                rev = st.get("revealed") or []
                if rev:
                    st["focus"] = rev[-1]
            if st.get("phase") == "linger":
                st["done"] = False
    return "keep"


def peek_exited(character_id: int) -> bool:
    return bool(_just_exited.get(character_id))


def overlay_text(character_id: int, mode: str = "user") -> str:
    with _lock:
        exited = _just_exited.pop(character_id, False)
        st = dict(_sessions[character_id]) if character_id in _sessions else None
    if exited:
        return reader.exit_note()
    if not st:
        return ""
    return reader.turn_task(st, mode)


def _steer_user(character_id: int, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    with _lock:
        st = _sessions.get(character_id)
        if not st:
            return messages
        last = str(st.get("last_text") or "")
        cue = reader.reading_cue(st, last)
    out = list(messages)
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") == "user":
            out[i] = {**out[i], "content": cue}
            break
    else:
        out.append({"role": "user", "content": cue})
    return out


def inject_overlay(
    character_id: int, messages: List[Dict[str, str]], mode: str = "user",
) -> List[Dict[str, str]]:
    playing = active(character_id)
    text = overlay_text(character_id, mode)
    if not text:
        return messages
    out = list(messages)
    user_mode = (mode or "user").lower() in ("user", "continue")
    if user_mode and playing:
        out = _steer_user(character_id, out)
    leading: List[Dict[str, str]] = []
    rest: List[Dict[str, str]] = []
    seen_body = False
    for m in out:
        if not seen_body and m.get("role") == "system":
            leading.append(m)
        else:
            seen_body = True
            rest.append(m)
    if playing:
        leading = [
            m for m in leading
            if not str(m.get("content") or "").startswith("长期记忆")
        ]
    leading.append({"role": "system", "content": text})
    if user_mode and playing:
        trailing: List[Dict[str, str]] = []
        cut_i = len(rest)
        while cut_i > 0 and rest[cut_i - 1].get("role") == "system":
            cut_i -= 1
            trailing.append(rest[cut_i])
        trailing.reverse()
        last_user_idx = None
        for i in range(cut_i - 1, -1, -1):
            if rest[i].get("role") == "user":
                last_user_idx = i
                break
        kept: List[Dict[str, str]] = []
        if last_user_idx is not None:
            kept.append(rest[last_user_idx])
            for m in rest[last_user_idx + 1:cut_i]:
                if m.get("role") == "assistant":
                    kept.append(m)
        return leading + kept + trailing
    return leading + rest
