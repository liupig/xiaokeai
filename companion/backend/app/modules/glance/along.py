"""陪我看：对方说了才一直看。

采集和识别在陪看开着时不停，包括她正在说的时候。
差分可以提前看一眼；电影、代码这类画面很静的时候，到了最大间隔也要看。
「别说了」只停主动开口。「别看了」才停下眼睛。
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from .situation import Offer, situation
from .watch import WatchSession

live = WatchSession(situation, lookup=True)
live.eyes_on = False

_START = ("陪我看", "陪着我看", "陪着看", "一直看着", "一直看我", "一起看", "打开视觉", "开启视觉", "视觉打开")
_PAUSE = ("暂时别陪看", "暂停陪看", "先别陪")
_STOP = (
    "别看了", "不用看了", "不要看了", "先别看", "不用陪", "别陪", "停止陪看", "不要陪了", "别看屏幕",
    "关掉视觉", "关闭视觉", "视觉关掉", "停止视觉",
)
_HUSH = ("别说了", "先安静", "别说话", "安静点", "先别说", "不要说", "少说点", "不用说", "别讲了")
_TALK = ("可以说了", "接着说", "你可以说话")
_HOLD_UNTIL_SEED = 8
_AFTER_SEED = 12
_GAP = 8
_QUIET = 30


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
    epoch: int = 0
    offer_epoch: int = 0
    speak_locked: bool = False
    trace_id: str = ""
    held: Offer | None = None
    held_trace: str = ""
    greeted: bool = False
    spoke_at: float = 0
    speaking: bool = False
    speak_since: float = 0


_lock = threading.Lock()
_state = _State()
_thread: threading.Thread | None = None
_halt = threading.Event()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def wants_pause(text: str) -> bool:
    compact = _compact(text)
    if not compact or len(compact) > 40:
        return False
    return any(word in compact for word in _PAUSE)


def wants_stop(text: str) -> bool:
    compact = _compact(text)
    if not compact or len(compact) > 80 or wants_pause(text):
        return False
    return any(word in compact for word in _STOP)


def wants_hush(text: str) -> bool:
    compact = _compact(text)
    if not compact or len(compact) > 40 or wants_stop(text):
        return False
    return any(word in compact for word in _HUSH)


def wants_talk(text: str) -> bool:
    compact = _compact(text)
    if not compact or len(compact) > 40:
        return False
    return any(word in compact for word in _TALK)


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


def _wait(seconds: float) -> bool:
    """停一下。返回 True 表示该退出，不再往下看。"""
    if _halt.wait(seconds):
        return True
    with _lock:
        return not _state.on


def stop() -> None:
    from .hearing import ear
    from .sense import reset as reset_sense
    from .service import abort_eyes_calls

    _halt.set()
    ear.stop()
    abort_eyes_calls()
    thread = _thread
    with _lock:
        running = bool(_state.on or _state.pending)
        if running:
            _state.on = False
            _state.pending = ""
            _state.last = ""
            _state.trail.clear()
            _state.said = ""
            _state.user_until = 0
            _state.offer = None
            _state.held = None
            _state.held_trace = ""
            _state.speak_locked = False
            _state.greeted = False
            _state.spoke_at = 0
            _state.speaking = False
            _state.speak_since = 0
            _state.epoch += 1
    if running:
        reset_sense()
        situation.reset()
        live.reset()
        live.eyes_on = False
        print("[along] stop")
    if thread is not None and thread is not threading.current_thread() and thread.is_alive():
        thread.join(timeout=2)


def start(character_id: int) -> None:
    global _thread
    if not character_id:
        return
    with _lock:
        if _state.on and _state.character_id == int(character_id) and _thread is not None and _thread.is_alive():
            return
    from .sense import reset as reset_sense

    reset_sense()
    with _lock:
        _halt.clear()
        _state.on = True
        _state.character_id = int(character_id)
        _state.hold_until = 0
        _state.offer = None
        _state.pending = ""
        _state.last = ""
        _state.trail.clear()
        _state.held = None
        _state.held_trace = ""
        _state.greeted = False
        _state.spoke_at = time.time()
        _state.speaking = False
        _state.speak_since = 0
        situation.reset()
        live.reset()
        live.eyes_on = True
        from .hearing import ear

        ear.start()
        alive = _thread is not None and _thread.is_alive()
        if not alive:
            _thread = threading.Thread(target=_loop, name="glance-along", daemon=True)
            _thread.start()
    print(f"[along] start cid={character_id}")


def pending_trace() -> str:
    with _lock:
        return _state.trace_id


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


def _sayable(offer: Offer | None) -> bool:
    """已经排给她的这一秒，不因为下一眼改了修订号就作废。太旧才丢掉。"""
    if offer is None or not (offer.summary or "").strip():
        return False
    return time.time() - float(offer.observation_time or 0) < 90


def candidate_alive() -> bool:
    with _lock:
        offer = _state.offer
        if offer is None or time.time() < _state.user_until:
            return False
        if _state.speak_locked or _state.offer_epoch != _state.epoch or not live.source_valid:
            return False
        return _sayable(offer)


def open_candidate(text: str, prior: list | None = None) -> str | None:
    """开口前复查。失效就丢掉，不把过期的评论交给她。"""
    with _lock:
        offer = _state.offer
        pending = _state.pending
        if not _state.on or offer is None or (text or "").strip() != pending.strip():
            return None
        if (
            _state.speak_locked
            or _state.offer_epoch != _state.epoch
            or time.time() < _state.user_until
            or not _sayable(offer)
        ):
            from .trace import mark

            mark(_state.trace_id, handoff_why="开口前这句已经过时，不交给她")
            _state.pending = ""
            _state.offer = None
            _state.trace_id = ""
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
        from .watch import screen_beat

        where = {
            "audio": "听到的一句",
            "window": "窗口里的一句",
        }.get(offer.channel) or {
            "movie": "片子里的一句",
            "music": "歌里的一句",
            "video": "画面里的一句",
            "code": "屏幕上的一句",
            "game": "这一局里的一句",
            "slides": "这一页上的一句",
        }.get(situation.scene, "眼前的一句")
        cue = screen_beat(
            offer.summary,
            attention=situation.attention,
            talk=situation.talk,
            where=where,
        )
        if talked:
            cue += "\n【刚说过】\n" + "\n".join(talked[-6:])
        prefs = _preferences(_state.character_id)
        if prefs:
            cue += "\n【长期】" + prefs
        cue += "\n" + situation.blocks()
        _state.speaking = True
        _state.speak_since = time.time()
        return cue[:700]


def _enqueue(offer: Offer, trace_id: str) -> None:
    """调用时已拿着锁。把这一句排给她，说完才能排下一句。"""
    from .trace import mark
    from .watch import Candidate

    live.candidate = Candidate(
        epoch=live.epoch,
        summary=offer.summary,
        topic_id=offer.topic_id,
        object_id=offer.object_id,
        key=offer.topic_id or offer.summary[:40],
        observation_time=offer.observation_time,
    )
    summary = offer.summary.strip()
    if summary == (_state.pending or "").strip():
        return
    if summary == (_state.last or "").strip() and time.time() - _state.spoke_at < _QUIET:
        return
    _remember(offer.summary)
    _state.greeted = True
    _state.offer = offer
    _state.pending = offer.summary
    _state.trace_id = trace_id
    _state.offer_epoch = _state.epoch
    mark(trace_id, handoff=offer.summary, handoff_why="已排给她，等她开口")
    _state.seq += 1
    print(f"[along] seq={_state.seq} {offer.summary[:40]}")


def finish_speak(spoke: bool, text: str = "") -> None:
    situation.note_offered(spoke)
    item = live.candidate
    if item is not None:
        live.considered[item.key] = live.clock
        if spoke and text.strip():
            live.speeches.append(text.strip())
            live.conversation_focus = item.object_id
            live.topic_possibilities = [item.object_id]
        else:
            live.silent_notes += 1
        live.candidate = None
    with _lock:
        _state.speaking = False
        _state.speak_since = 0
        if spoke:
            _state.spoke_at = time.time()
            _state.greeted = True
        _state.pending = ""
        _state.offer = None
        held = _state.held
        if held is not None and _sayable(held) and time.time() >= _state.user_until and not _state.speak_locked:
            trace_id = _state.held_trace
            _state.held = None
            _state.held_trace = ""
            _enqueue(held, trace_id)
    if spoke:
        from .hearing import ear

        ear.hush(12)


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
    if wants_stop(text):
        stop()
        from .eyes_host import shutdown

        shutdown()
        return
    if wants_start(text) and harness:
        from .eyes_host import enable_glance, ensure

        enable_glance()
        ensure()
        glance = True
    if not glance or not harness:
        stop()
        return
    if wants_start(text):
        start(character_id)
    with _lock:
        if _state.on:
            # 用户的话走旁路。排队的和正在生成的主动陪看都绑在旧 epoch 上，不补说。
            heard = live.user_says(text)
            _state.epoch = live.epoch
            _state.user_until = time.time() + 12
            _state.pending = ""
            _state.offer = None
            _state.speak_locked = live.speak_locked
            spoken = " ".join((text or "").split())
            if spoken:
                _state.said = spoken[:80]


def release_user_turn() -> None:
    with _lock:
        _state.user_until = 0
        if _state.on:
            live.finish_user_turn()


def _preferences(character_id: int) -> str:
    if not character_id:
        return ""
    try:
        from ..memory.worker import list_facts

        rows = list_facts(int(character_id))
    except Exception:
        return ""
    lines = [str(item.get("content") or "")[:40] for item in rows if item.get("kind") == "preference" and item.get("content")]
    return "；".join(lines[:3])


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


def _company_offer() -> Offer | None:
    """一起看时，新的一秒、开场，或安静了半分钟，都交给她。闸门嫌浅也交。"""
    point = " ".join((situation.progress or "").split())
    if not point or quiet_line(point):
        return None
    with _lock:
        if not _state.on or _state.speak_locked:
            return None
        same = point == _state.last or same_scene(point, _state.last)
        if _state.greeted and same and time.time() - _state.spoke_at < _QUIET:
            return None
    return Offer(
        scene_id=situation.scene_id,
        object_id=situation.latest_object_id or situation.object_id,
        topic_id=situation.topic_id or f"company:{point[:40]}",
        observation_time=time.time(),
        revision=situation.revision,
        summary=point[:180],
        channel=situation.channel,
    )


_last_model = 0.0


def _loop() -> None:
    global _last_model
    from .watch import INTERVALS

    while True:
        with _lock:
            if not _state.on:
                return
            character_id = _state.character_id
            speak_locked = _state.speak_locked
            queued = bool(_state.pending)
        from .hearing import ear

        ear.set_quiet(speak_locked or queued)
        if not _modules_on():
            stop()
            return
        if _tarot_now(character_id):
            if _wait(4):
                return
            continue
        if not live.eyes_on:
            if _wait(1):
                return
            continue
        if live.eyes_down and time.monotonic() < live.retry_after:
            if _wait(0.4):
                return
            continue
        scene = situation.scene or "unknown"
        force = (time.time() - _last_model) >= INTERVALS.get(scene, 10.0)
        from .sense import collect

        found = collect(force=force, before=situation.eyes_before(), echo=list(live.speeches[-3:]), timeout=90)
        if _halt.is_set():
            return
        from .trace import mark

        trace_id = str(found.get("trace_id") or "")
        now = time.monotonic()
        if not found.get("ok"):
            mark(trace_id, handoff_why="眼睛没看成，不交给她")
            live.pulse(now, eyes_ok=False)
            if _wait(0.4):
                return
            continue
        gap = str(found.get("continuity_gap") or "")
        live.pulse(now, gap=gap)
        if found.get("used_eyes") and found.get("ok"):
            _last_model = time.time()
            live.last_look_at = live.clock
        text = str(found.get("text") or "").strip()
        stale_look = bool(found.get("skipped") or quiet_line(text))
        offer = None
        if not stale_look:
            from .situation import parse_observation

            obs = parse_observation(
                text,
                source=str(found.get("source") or "screen"),
                timestamp=found.get("observed_at"),
            )
            obs.channel = str(found.get("channel") or "")
            if found.get("observation_id"):
                obs.observation_id = str(found.get("observation_id"))
            offer = situation.ingest(obs, allow_offer=not speak_locked and live.source_valid and not live.plan_standby)
            offer = live.admit(obs, offer)
        elif text and not found.get("skipped"):
            from .situation import parse_observation

            quiet_obs = parse_observation(
                text,
                source=str(found.get("source") or "screen"),
                timestamp=found.get("observed_at"),
            )
            quiet_obs.channel = str(found.get("channel") or "")
            situation.ingest(quiet_obs, allow_offer=False)
            live.admit(quiet_obs, None)
        if offer is None and not speak_locked:
            offer = _company_offer()
        if offer is not None:
            # 识别本身要几十秒。排给她时从这一刻算，不要拿截图时刻把刚看完的句子判成过期。
            offer.observation_time = time.time()
        if offer is None:
            if speak_locked:
                why = "你让她先别说，只看不交"
            elif stale_look:
                why = "没有新的屏幕事实，不交给她"
            else:
                why = "没有值得交给她的点"
            mark(trace_id, handoff_why=why)
            if _wait(2 if found.get("skipped") else 1):
                return
            continue
        hold_speech = False
        with _lock:
            if not _state.on:
                return
            if _state.speaking and time.time() - _state.speak_since < 20:
                hold_speech = True
                if (
                    offer is not None
                    and _sayable(offer)
                    and offer.summary.strip() != (_state.pending or "").strip()
                ):
                    _state.held = offer
                    _state.held_trace = trace_id
                    why = "她正在说上一句，这一眼先拿着"
                else:
                    why = "她正在说这一句"
                mark(trace_id, handoff_why=why)
        if hold_speech:
            if _wait(0.4):
                return
            continue
        with _lock:
            if not _state.on:
                return
            newer = (
                offer is not None
                and _sayable(offer)
                and offer.summary.strip() != (_state.pending or "").strip()
                and time.time() >= _state.user_until
                and not _state.speak_locked
            )
            if _state.pending and newer:
                _state.pending = ""
                _state.offer = None
            elif _state.pending and not _sayable(_state.offer):
                _state.pending = ""
                _state.offer = None
                print("[along] drop stale")
            if (
                not _state.pending
                and _state.held is not None
                and _sayable(_state.held)
                and (offer is None or not _sayable(offer))
            ):
                offer = _state.held
                trace_id = _state.held_trace or trace_id
                _state.held = None
                _state.held_trace = ""
            busy = bool(_state.pending) or time.time() < _state.user_until or time.time() < _state.hold_until
            if busy or _state.speak_locked or offer is None or not _sayable(offer):
                if (
                    offer is not None
                    and _sayable(offer)
                    and busy
                    and not _state.speak_locked
                    and (_state.offer is None or offer.topic_id != _state.offer.topic_id)
                ):
                    _state.held = offer
                    _state.held_trace = trace_id
                    why = "这一点先记下，等这句说完再交"
                elif _state.speak_locked:
                    why = "你让她先别说，只看不交"
                elif busy:
                    why = "上一句还没说完，或你正在说话，这一眼先不交"
                elif offer is None:
                    why = "没有值得交给她的点"
                else:
                    why = "这个点已经过时，丢掉"
                mark(trace_id, handoff_why=why)
                if _wait(1):
                    return
                continue
            _enqueue(offer, trace_id)
        if _wait(1):
            return
