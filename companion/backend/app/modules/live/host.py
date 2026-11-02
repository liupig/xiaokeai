"""直播主持。开播后按节目单取队列，生成一句，等舞台念完再取下一句。"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any, Callable

from .audience import AudienceBook
from .commands import act_line, allowed_act, blocked
from .budget import SessionBudget
from .config import feature_on, missing_acks, normalize, song_titles
from .director import speak_events, speak_idle
from .events import PRIORITY_KINDS, LiveEvent
from .queue import LiveQueue
from .intake import EventIntake
from .rundown import Rundown
from .show import GuessGame, TopicDeck, WishPool

Complete = Callable[[dict, list[dict]], tuple[str, int]]


class Health:
    def __init__(self) -> None:
        self.started = 0.0
        self.last_tick = 0.0
        self.last_error = ""
        self.llm_failures = 0
        self.degraded = False

    def note(self, message: str) -> None:
        self.last_error = (message or "")[:180]

    def public(self, now: float) -> dict:
        uptime = int(now - self.started) if self.started else 0
        lag = now - self.last_tick if self.last_tick else 0
        return {
            "uptime_sec": max(0, uptime),
            "last_error": self.last_error,
            "llm_failures": self.llm_failures,
            "degraded": self.degraded or (self.started > 0 and lag > 15),
            "tick_lag_sec": int(lag) if self.last_tick else 0,
        }


class LiveHost:
    def __init__(self) -> None:
        self.queue = LiveQueue()
        self.intake = EventIntake()
        self._generation = 0
        self._generating = False
        self._gift_streak = 0
        self._dialogue: deque[dict] = deque(maxlen=4)
        self._turn_context: dict | None = None
        self._playback_failures = 0
        self._playback_owner = ""
        self.audience = AudienceBook()
        self.budget = SessionBudget()
        self.rundown = Rundown()
        self.topics = TopicDeck()
        self.game = GuessGame()
        self.wishes = WishPool()
        self.health = Health()
        self.on_air = False
        self.character_id = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._override: dict | None = None
        self._cfg_cache: dict | None = None
        self._cfg_at = 0.0
        self._name = ""
        self._persona = ""
        self._complete: Complete | None = None
        self._turn: dict | None = None
        self._turn_at = 0.0
        self._last_spoke = 0.0
        self._busy = False
        self._busy_at = 0.0
        self._last_audience = 0.0
        self._cue = ""
        self._seq = 0
        self._n = 0
        self._instance_id = uuid.uuid4().hex[:12]
        self._fired: set[int] = set()
        self._recent: deque[str] = deque(maxlen=8)
        self._board: deque[dict] = deque(maxlen=80)
        self._douyin_at = 0.0
        self._bili = None
        self._bili_status: dict[str, Any] = {
            "state": "idle", "error": "", "anchor": "", "room_id": "", "reconnects": 0,
        }

    def use_overrides(self, cfg: dict, *, name: str = "小可爱", persona: str = "",
                      complete: Complete | None = None) -> None:
        self._override = normalize(cfg)
        self._name = name
        self._persona = persona
        self._complete = complete

    def cfg(self) -> dict:
        if self._override is not None:
            return self._override
        now = time.time()
        if self._cfg_cache is not None and now - self._cfg_at < 1:
            return self._cfg_cache
        try:
            from sqlmodel import Session

            from ...db import engine
            from ...services import settings_store

            with Session(engine) as session:
                raw = settings_store.get_all(session).get("live")
            cfg = normalize(raw)
        except Exception:
            cfg = normalize({})
        self._cfg_cache = cfg
        self._cfg_at = now
        return cfg

    def _character(self) -> tuple[str, str]:
        if self._name:
            return self._name, self._persona
        if not self.character_id:
            return "小可爱", ""
        try:
            from sqlmodel import Session

            from ...db import engine
            from ...models import Character

            with Session(engine) as session:
                row = session.get(Character, self.character_id)
            if row is None:
                return "小可爱", ""
            return (row.name or "小可爱"), (row.persona or "")[:600]
        except Exception:
            return "小可爱", ""

    def _llm(self) -> tuple[dict, dict]:
        if self._override is not None:
            budget = self._override.get("budget") or {}
            return {}, {
                "base_url": budget.get("fallback_base_url") or "",
                "api_key": budget.get("fallback_api_key") or "",
                "model": budget.get("fallback_model") or "",
            }
        try:
            from sqlmodel import Session

            from ...db import engine
            from ...services import settings_store

            with Session(engine) as session:
                llm = dict(settings_store.get_all(session).get("llm") or {})
        except Exception:
            llm = {}
        budget = self.cfg().get("budget") or {}
        fallback = {
            "base_url": budget.get("fallback_base_url") or "",
            "api_key": budget.get("fallback_api_key") or "",
            "model": budget.get("fallback_model") or "",
            "temperature": llm.get("temperature", 0.85),
            "top_p": llm.get("top_p", 1.0),
        }
        return llm, fallback

    def loop_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def ensure_loop(self) -> None:
        if self.loop_alive():
            return
        self._stop.clear()
        self.health.degraded = False
        thread = threading.Thread(target=self._loop, name="live-host", daemon=True)
        self._thread = thread
        thread.start()

    def shutdown(self) -> None:
        self.go_off()
        self._stop.set()
        self.stop_bilibili()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception as exc:
                self.health.note(str(exc))
                self.health.degraded = True
            self._stop.wait(2)

    def go_on(self, character_id: int, now: float | None = None) -> dict:
        cfg = self.cfg()
        missing = missing_acks(cfg)
        if missing:
            return {"ok": False, "missing": missing}
        now = time.time() if now is None else now
        with self._lock:
            self.on_air = True
            self._generation += 1
            self.queue.clear()
            self._dialogue.clear()
            self._recent.clear()
            self._gift_streak = 0
            self.character_id = int(character_id or 0)
            self.health.started = now
            self.health.last_error = ""
            self._last_spoke = now
            self._fired.clear()
            self._turn = None
            self._cue = ""
            self._last_audience = now
            self.budget.reset()
            self.rundown.start(now)
            self.game = GuessGame()
        self.ensure_loop()
        return {"ok": True, "missing": []}

    def go_off(self) -> None:
        with self._lock:
            self.on_air = False
            self._generation += 1
            self._turn = None
            self._busy = False
            self.queue.clear()

    def note_busy(self, busy: bool, character_id: int = 0) -> None:
        with self._lock:
            self._busy = bool(busy)
            self._busy_at = time.time()
            if character_id:
                self.character_id = int(character_id)

    def claim(self, turn_id: str, player_id: str) -> bool:
        with self._lock:
            if not player_id or not self._turn or self._turn["id"] != turn_id:
                return False
            if self._playback_owner and self._playback_owner != player_id:
                return False
            self._playback_owner = player_id
            return True

    def ack(self, turn_id: str, outcome: str = "completed", player_id: str = "") -> bool:
        with self._lock:
            if self._playback_owner and player_id != self._playback_owner:
                return False
            if self._turn and self._turn.get("id") == turn_id:
                if outcome in ("completed", "displayed"):
                    self._recent.append(self._turn["text"][:80])
                    if self._turn_context:
                        self._dialogue.append(self._turn_context)
                elif outcome == "failed":
                    self._playback_failures += 1
                    self.health.note("直播语音播放失败，请检查语音引擎和音频输出")
                self._turn = None
                self._turn_context = None
                self._playback_owner = ""
                return True
            return False

    def reset_budget(self) -> None:
        with self._lock:
            self.budget.reset()

    def ingest(self, ev: LiveEvent, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        cfg = self.cfg()
        if ev.platform == "bilibili" and not feature_on(cfg, "bilibili"):
            return False
        if ev.platform == "douyin" and not feature_on(cfg, "douyin"):
            return False
        if ev.platform == "rehearsal" and not feature_on(cfg, "rehearsal"):
            return False
        if ev.kind == "comment" and blocked(ev.content, str(cfg.get("block_words") or "")):
            return False
        with self._lock:
            ev = self.intake.accept(ev)
            if ev is None:
                return False
            self._remember(ev)
            if ev.kind == "like" or (ev.kind in PRIORITY_KINDS and not feature_on(cfg, "gifts")):
                return False
            if feature_on(cfg, "audience"):
                self.audience.note(ev)
            if feature_on(cfg, "ritual"):
                self.wishes.note(ev)
            if ev.platform == "douyin":
                self._douyin_at = now
            if ev.kind in ("comment", "gift", "superchat", "guard", "follow"):
                self._last_audience = now
            return self.queue.offer(ev, now=now, cfg=cfg)

    def _remember(self, ev: LiveEvent) -> None:
        self._seq += 1
        ev.seq = self._seq
        self._board.append(ev.public())

    def tick_once(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self.health.last_tick = now
            self.health.degraded = False
            if not self.on_air:
                return
            if self._generating:
                return
            self.queue.prune(now)
            if self._stop_for_guard(now, cfg := self.cfg()):
                self.on_air = False
                self._generation += 1
                self._turn = None
                self._busy = False
                self.queue.clear()
                return
            if self._turn is not None:
                if now - self._turn_at > 90:
                    self._turn = None
                    self.health.note("上一句超过 90 秒没被舞台确认")
                else:
                    return
            if self._busy and now - self._busy_at < 90:
                return
            plan = self._plan(now)
            cfg = self.cfg()
            generation = self._generation
            if plan is not None:
                self._generating = True
        if plan is None:
            return
        turn = None
        try:
            turn = self._realize(plan, cfg)
        finally:
            with self._lock:
                self._generating = False
                if turn is not None and self.on_air and generation == self._generation and self._turn is None:
                    self._turn = turn
                    self._playback_owner = ""
                    self._turn["sources"] = [
                        {**ev.public(), "msg_id": ev.msg_id} for ev in plan.get("events", [])
                    ]
                    self._turn["created_at"] = now
                    self._turn_at = now
                    self._last_spoke = now
                    self._turn_context = None
                    if plan.get("events"):
                        self._turn_context = {
                            "viewers": [{"name": ev.nickname, "text": ev.content} for ev in plan["events"]],
                            "reply": turn["text"],
                        }

    def _plan(self, now: float) -> dict | None:
        cfg = self.cfg()
        if self._gift_streak >= 2:
            batch = self.queue.take_batch(now, cfg)
            if batch:
                self._gift_streak = 0
                return {"type": "batch", "events": batch, "mode": "chat"}
        jumped = self.queue.take_priority(cfg)
        if jumped:
            self._gift_streak += 1
            return {
                "type": "batch", "events": jumped, "mode": "chat",
                "interrupt": feature_on(cfg, "interrupt") and any(ev.kind == "superchat" for ev in jumped),
            }
        if self._cue:
            act = self._cue
            self._cue = ""
            return {"type": "act", "act": act}
        song = self.queue.take_song(cfg)
        if song:
            ev, title = song
            return {"type": "song_request", "event": ev, "title": title}
        acted = self.queue.take_act(cfg)
        if acted:
            ev, act = acted
            return {"type": "act", "act": act, "event": ev}
        seg = self.rundown.current(now, cfg)
        if seg["id"] == "game" and feature_on(cfg, "rundown"):
            if self.game.open:
                found = self.queue.take_guess()
                if found:
                    ev, number = found
                    return {"type": "guess", "event": ev, "number": number}
            elif self.game.should_announce(seg["index"]):
                return {"type": "announce", "index": seg["index"]}
        if seg["id"] in ("dance", "song", "wish") and seg["index"] not in self._fired:
            self._fired.add(seg["index"])
            return {"type": seg["id"], "index": seg["index"]}
        batch = self.queue.take_batch(now, cfg)
        if batch:
            self._gift_streak = 0
            mode = "read" if seg["id"] == "read" else "chat"
            return {"type": "batch", "events": batch, "mode": mode}
        idle_sec = int(cfg["pace"]["idle_sec"])
        if feature_on(cfg, "idle") and now - self._last_spoke >= idle_sec:
            if seg["id"] in ("chat", "read", "wish"):
                return {"type": "idle"}
        return None

    def _realize(self, plan: dict, cfg: dict) -> dict | None:
        kind = plan["type"]
        if kind == "dance":
            return self._make("我跳一段。", "dance")
        if kind == "song":
            titles = song_titles(cfg)
            if not titles:
                return None
            title = titles[int(plan["index"]) % len(titles)]
            return self._make(f"这一首《{title}》放给在场的人。点歌只放已经授权的。", "song")
        if kind == "song_request":
            title = str(plan.get("title") or "")
            who = plan["event"].nickname
            return self._make(f"{who}点的《{title}》，放给在场的人。", "song")
        if kind == "act":
            act = str(plan.get("act") or "")
            line = act_line(act) or "好。"
            cue = "dance" if act == "dance" else "act"
            return self._make(line, cue, act=act)
        if kind == "wish":
            item = None
            with self._lock:
                item = self.wishes.pop()
            if item is None:
                return None
            return self._make(f"{item['name']}许愿：{item['text']}。我记下了。", "wish")
        if kind == "announce":
            return self._make(self.game.announce(int(plan["index"])), "game")
        if kind == "guess":
            ev = plan["event"]
            line = self.game.answer(ev.nickname, int(plan["number"]))
            if not line:
                return None
            return self._make(line, "game")
        if kind == "idle":
            return self._idle_turn(cfg)
        if kind == "batch":
            return self._batch_turn(
                plan["events"], cfg, plan.get("mode") or "chat", bool(plan.get("interrupt")),
            )
        return None

    def _idle_turn(self, cfg: dict) -> dict:
        seed = self.topics.next()
        name, persona = self._character()
        audience = self.audience.prompt(cfg)
        primary, fallback = self._llm()
        try:
            text, tokens = speak_idle(
                cfg=cfg, name=name, persona=persona, seed=seed, audience=audience,
                budget_open=self.budget.tripped(cfg), primary=primary, fallback=fallback,
                complete=self._complete or _default_complete(),
            )
        except Exception:
            text, tokens = seed, 0
        if tokens:
            self.budget.add(cfg, tokens)
        return self._make(text or seed, "idle")

    def _batch_turn(self, events: list[LiveEvent], cfg: dict, mode: str, interrupt: bool = False) -> dict:
        phrase = str((cfg.get("persona") or {}).get("catchphrase") or "我在呢")
        if not feature_on(cfg, "reply"):
            from .director import canned
            text, cue = canned(events, phrase)
            return self._make(text, cue, interrupt=interrupt)
        name, persona = self._character()
        audience = self.audience.prompt(cfg)
        primary, fallback = self._llm()
        complete = self._complete or _default_complete()
        try:
            text, cue, tokens = speak_events(
                events, cfg=cfg, name=name, persona=persona, mode=mode,
                audience=audience, recent=list(self._recent),
                budget_open=self.budget.tripped(cfg), primary=primary, fallback=fallback,
                complete=complete,
                dialogue=list(self._dialogue),
            )
            if tokens:
                self.budget.add(cfg, tokens)
        except Exception as exc:
            self.health.llm_failures += 1
            self.health.note(str(exc))
            self.budget.fail()
            from .director import canned
            text, cue = canned(events, phrase)
        return self._make(text, cue, interrupt=interrupt)

    def _make(self, text: str, cue: str, act: str = "", interrupt: bool = False) -> dict:
        spoken = (text or "").strip()
        if not spoken:
            spoken = "我在。"
        self._n += 1
        return {
            "id": f"{self._instance_id}-t{self._n}",
            "text": spoken[:240],
            "cue": cue or "chat",
            "act": act or "",
            "interrupt": bool(interrupt),
        }

    def push_cue(self, act: str) -> bool:
        name = allowed_act(act)
        if not name or not feature_on(self.cfg(), "commands"):
            return False
        with self._lock:
            self._cue = name
        self.ensure_loop()
        return True

    def _stop_for_guard(self, now: float, cfg: dict) -> bool:
        pace = cfg.get("pace") or {}
        cap = int(pace.get("session_max_min") or 0)
        if cap and self.health.started and now - self.health.started >= cap * 60:
            self.health.note(f"单场到了 {cap} 分钟，已停播")
            return True
        quiet = int(pace.get("quiet_min") or 0)
        if quiet and self._last_audience and now - self._last_audience >= quiet * 60:
            self.health.note(f"冷场 {quiet} 分钟，已停播")
            return True
        return False

    def start_bilibili(self) -> dict:
        cfg = self.cfg()
        bili = cfg.get("bilibili") or {}
        if not feature_on(cfg, "bilibili"):
            return {"ok": False, "error": "哔哩哔哩开关是关的"}
        if not bili.get("access_key_id") or not bili.get("access_key_secret"):
            return {"ok": False, "error": "先填开放平台的 Access Key"}
        if not int(bili.get("app_id") or 0) or not bili.get("code"):
            return {"ok": False, "error": "先填应用 ID 和身份码"}
        self.stop_bilibili()
        from .bili.client import OpenLiveSession

        session = OpenLiveSession(
            bili["access_key_id"], bili["access_key_secret"], int(bili["app_id"]), bili["code"],
            on_event=self.ingest, on_status=self._on_bili,
        )
        self._bili = session
        session.start()
        self.ensure_loop()
        return {"ok": True, "error": "", **session.snapshot()}

    def stop_bilibili(self) -> dict:
        session = self._bili
        self._bili = None
        if session is not None:
            session.stop()
            self._bili_status = session.snapshot()
        return {"ok": True, **self._bili_status}

    def _on_bili(self, status: dict) -> None:
        self._bili_status = dict(status)
        if status.get("error"):
            self.health.note(str(status["error"]))

    def snapshot(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        cfg = self.cfg()
        with self._lock:
            seg = self.rundown.current(now, cfg) if self.on_air else {"id": "chat", "index": 0, "left": 0}
            ago = int(now - self._douyin_at) if self._douyin_at else -1
            bili = dict(self._bili_status)
            if self._bili is not None:
                bili["reconnects"] = self._bili.reconnects
            return {
                "on_air": self.on_air,
                "missing": missing_acks(cfg) if not self.on_air else [],
                "features": dict(cfg.get("features") or {}),
                "segment": seg,
                "budget": self.budget.public(cfg),
                "health": self.health.public(now),
                "bilibili": bili,
                "douyin": {
                    "callback": "/api/modules/live/douyin/callback",
                    "room_id": str((cfg.get("douyin") or {}).get("room_id") or ""),
                    "last_ago": ago,
                },
                "events": list(self._board)[-30:],
                "turn": dict(self._turn) if self._turn else None,
                "regulars": len(self.audience.regulars(cfg, limit=20)),
                "wishes": self.wishes.pending(),
                "ai_label": feature_on(cfg, "ai_label"),
                "schedule": str((cfg.get("schedule") or {}).get("note") or ""),
                "community": str((cfg.get("schedule") or {}).get("community") or ""),
                "queue": len(self.queue),
                "processing": {"intake": self.intake.public(), "expired": self.queue.expired,
                               "overflow": self.queue.dropped, "generating": self._generating,
                               "playback_failures": self._playback_failures},
            }


def _default_complete():
    from .director import complete_text
    return complete_text


host = LiveHost()
