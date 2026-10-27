"""屏幕时间线和对话主题。

采集、识别、开口是三条线。这里用模拟时间把它们走完，不调用视觉模型。
眼睛只交事实。她说不说仍由外面的 dsh 决定，本模块只保管候选和 epoch。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .situation import Situation, parse_observation

INTERVALS = {
    "movie": 12.0,
    "code": 18.0,
    "music": 8.0,
    "video": 5.0,
    "slides": 15.0,
    "game": 8.0,
    "unknown": 10.0,
}
BUFFER = 48
OVERLAP = 3
QUEUE_CAP = 2
LOG_CAP = 32
CUE_CAP = 700
COALESCE = 1.5
PLAN_IDLE = 40.0
CONSIDER_AGE = 30.0
BACKOFF = (1.0, 2.0, 4.0, 8.0)

_HUSH = ("别说了", "先安静", "别说话", "安静点", "先别说", "不要说", "少说点", "不用说", "别讲了")
_PAUSE = ("暂时别陪看", "暂停陪看", "先别陪")
_LOOK_OFF = ("别看了", "不用看了", "不要看了", "先别看", "别看屏幕")
_LOOK_ON = ("可以看了", "继续看", "接着看")
_TALK_ON = ("可以说了", "接着说", "你可以说话", "多说点", "说多点", "多讲点", "多聊聊")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def event_key(scene: str, object_id: str, texts: list[str], progress: str) -> str:
    gist = next((item.strip() for item in texts if item.strip()), "") or (progress or "").strip()
    kept = re.sub(r"\s+", "", gist)[:48] or "none"
    return f"{scene}|{object_id}|{kept}"


def _json_text(raw: str) -> str:
    """从一句可能写坏的 JSON 里只取出她要说的话。"""
    import json
    matched = re.search(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', raw or "")
    if not matched:
        return ""
    try:
        return str(json.loads(f'"{matched.group(1)}"') or "").strip()
    except json.JSONDecodeError:
        return matched.group(1).strip()


_HOLLOW = (
    "安安静静", "不用说话", "不用多说", "就在这儿陪", "就在这里陪",
    "陪着你", "陪着一起", "一起看", "慢慢看", "你看你的", "坐着陪",
    "有新情况", "有新画面", "马上跟你说", "跟你说", "挺好的", "新情况",
)

def along_turn(talk: str = "normal") -> str:
    """开口时告诉她眼前发生了什么。感受由她自己来，空的陪伴不算接上。"""
    more = "他想多听一点，可以再多接一句。" if talk == "more" else ""
    return (
        "对方没说话。你正和他一起看，一句接一句，不要停在上一句。"
        "【眼前】引号里这句才是现在发生的。就接这句，说你的反应。"
        "不要把原句再念一遍，不要接着更早的事，不要说你在安安静静陪着，没有的不要编。"
        "只有这一句和你刚说过的是同一件事，才可以不说。"
        + more
    )


def _half_heard(line: str) -> bool:
    """太短、又没有说完的口气。这种只能接听清的感受，不能补剧情。"""
    text = (line or "").strip()
    han = re.findall(r"[\u4e00-\u9fff]", text)
    if not 4 <= len(han) <= 5:
        return False
    return re.search(r"[啊呢吗吧呀！？?!]$", text) is None


def screen_beat(line: str, attention: str = "", talk: str = "", where: str = "片子里的一句") -> str:
    """交给她的现场。画面里的那一句，加上他刚才要留意的、想听多少。"""
    said = " ".join((line or "").split())
    mark = "（没听全）" if _half_heard(said) else ""
    lines = [f"{where}{mark}：「{said}」"]
    if attention and attention not in {"字幕", "台词", "原文", "标题"}:
        lines.append(f"他在看的是：{attention}。没有的不要编。")
    if talk == "more":
        lines.append("他想多听一点，仍然只说画面里的事")
    return "\n".join(lines)


def hollow_company(line: str) -> bool:
    """只有「陪着、安静」或在描述左右和张数，没有画面里的事。这种不能当互动。"""
    if re.search(r"这句原文|这里写着|这里出现了|安安静静|陪你看|陪着你|乖乖|不碰|放好|没看到新", line or ""):
        return True
    if re.search(r"画面切|左侧|右侧|左边|右边|\d+\s*张|点赞|动漫角色|评论区", line or "") and not re.search(
        r"[\"“「『].+[\"”」』]", line or ""
    ):
        return True
    compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", line or "")
    removed = False
    for word in _HOLLOW:
        if word in compact:
            compact = compact.replace(word, "")
            removed = True
    compact = re.sub(
        r"好呀|好的|好吧|我们就|我们|这个|那个|画面|直播|电影|视频|呀|呢|吧|啦|哦|啊|的|了|就|在|看",
        "",
        compact,
    )
    return len(compact) <= 4 if removed else len(compact) < 4


def parse_reaction(text: str, expected_topic: str) -> tuple[str, str] | None:
    """她的回复。话题对不上就丢掉。JSON 外壳不能当成要说的话。"""
    import json
    raw = re.sub(r"\[[^\]]*\]", "", text or "").strip()
    if not raw or raw.lower() in {"silent", "[silent]"} or raw in {"不说", "不说。", "不说."}:
        return ("silent", "")
    data = None
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            data = None
    looks_like_json = "{" in raw and ("action" in raw or "topic_id" in raw or '"text"' in raw)
    if isinstance(data, dict) and ("action" in data or "text" in data or "topic_id" in data):
        action = str(data.get("action") or "").strip().lower()
        topic = str(data.get("topic_id") or "")
        if topic and expected_topic and topic != expected_topic:
            return None
        if action == "silent":
            return ("silent", "")
        said = str(data.get("text") or "").strip()
        if action == "speak" or said:
            return ("speak", said) if said else ("silent", "")
        return ("silent", "")
    if looks_like_json:
        said = _json_text(raw)
        return ("speak", said) if said else ("silent", "")
    if not expected_topic:
        return None
    return ("speak", raw)


def classify_turn(text: str) -> str:
    """用户下一句：继续、在回应她，还是新话题。含糊就保持多种可能。"""
    raw = (text or "").strip()
    if not raw:
        return "unclear"
    if any(word in raw for word in ("换个话题", "不说这个", "另外", "晚饭", "别的事")):
        return "new"
    if any(word in raw for word in ("你刚说", "你说的", "对啊", "哈哈", "就是这句", "回应")):
        return "reply"
    if any(word in raw for word in ("接着", "然后呢", "继续", "还是刚才")):
        return "continue"
    if len(_compact(raw)) <= 2:
        return "unclear"
    return "unclear"


@dataclass
class _Frame:
    seq: int
    t: float
    changed: bool
    text: str
    scene: str


@dataclass
class _Job:
    seq_end: int
    seq_start: int
    t: float
    text: str
    scene: str
    changed: bool
    forced: bool


@dataclass
class Candidate:
    epoch: int
    summary: str
    topic_id: str
    object_id: str
    key: str
    observation_time: float


class WatchSession:
    def __init__(self, bound: Situation | None = None, *, lookup: bool = False) -> None:
        self.situation = bound if bound is not None else Situation()
        self.lookup = lookup
        self._looked_title = ""
        self.turn_kind = ""
        self.seq = 0
        self.clock = 0.0
        self.frames: list[_Frame] = []
        self.queue: list[_Job] = []
        self.paused = False
        self.held: list[_Job] = []
        self.applied_through = 0
        self.last_window_end = 0
        self.last_look_at = -1e9
        self.looks = 0
        self.forced_looks = 0
        self.coalesced = 0
        self.failed_attempts = 0
        self.recovery_looks = 0
        self.eyes_down = False
        self.source_valid = True
        self.eyes_on = True
        self.speak_locked = False
        self.segment = 1
        self.gaps: list[str] = []
        self.log: list[dict] = []
        self.archived = 0
        self.events: dict[str, dict] = {}
        self.considered: dict[str, float] = {}
        self.epoch = 0
        self.candidate: Candidate | None = None
        self.inflight_epoch = 0
        self.inflight: _Job | None = None
        self.windows: list[tuple[int, int]] = []
        self.blocked_object = ""
        self.speeches: list[str] = []
        self.silent_notes = 0
        self.dropped_late = 0
        self.n_offers = 0
        self.screen_focus = ""
        self.conversation_focus = ""
        self.topic_possibilities: list[str] = []
        self.conversation_until = 0.0
        self.plan_standby = False
        self.last_progress_at = 0.0
        self.last_progress = ""
        self._retry_at = 0.0
        self.retry_after = 0.0
        self._retry_step = 0
        self._was_down = False
        self.captured_while_off = 0
        self.max_queue = 0

    def reset(self) -> None:
        bound = self.situation
        lookup = self.lookup
        self.__init__(bound, lookup=lookup)

    def _maybe_lookup(self, obs) -> None:
        if not self.lookup:
            return
        title = (getattr(obs, "title", "") or "").strip()
        scene = self.situation.scene
        if scene not in {"movie", "music"} or not title or float(getattr(obs, "name_confidence", 0) or 0) < 0.6:
            return
        if title == self._looked_title:
            return
        self._looked_title = title
        from .background import schedule

        artist = self.situation.artist

        def apply(lines: list[str]) -> None:
            if self.situation.title != title:
                return
            self.situation.background = lines
            if not lines and "没有确认不含剧透的背景" not in self.situation.unknowns:
                self.situation.unknowns.append("没有确认不含剧透的背景")

        schedule(scene, title, artist, apply)

    def admit(self, obs, offer):
        """眼睛已经看过的一条结果。重复事件不重新交点。"""
        stamp = float(getattr(obs, "timestamp", 0) or 0)
        if stamp < self.clock:
            stamp = self.clock
        self.clock = stamp
        self.seq += 1
        self._age(self.clock)
        progress = self.situation.progress
        key = event_key(
            self.situation.scene,
            self.situation.latest_object_id,
            list(getattr(obs, "visible_text", []) or []) or list(getattr(obs, "visible_events", []) or []),
            progress,
        )
        already = bool(self.events.get(key, {}).get("open"))
        if progress and progress != self.last_progress and not already:
            self.last_progress = progress
            self.last_progress_at = self.clock
            self.plan_standby = False
        job = _Job(self.seq, self.seq, self.clock, getattr(obs, "raw", "") or "", self.situation.scene, True, False)
        self._touch_event(key, self.clock, self.situation.latest_object_id)
        self._remember(job, key)
        if already or (key in self.considered and self.events.get(key, {}).get("open")):
            return None
        if self.speak_locked or not self.eyes_on or not self.source_valid or self.plan_standby:
            return None
        if offer is not None and offer.object_id == self.blocked_object:
            return None
        self._maybe_lookup(obs)
        if offer is None:
            return None
        if self.candidate is not None and self.candidate.key != key:
            self.candidate = None
        if self.candidate is not None:
            return None
        self.n_offers += 1
        self.candidate = Candidate(
            epoch=self.epoch,
            summary=offer.summary,
            topic_id=offer.topic_id,
            object_id=offer.object_id,
            key=key,
            observation_time=float(getattr(obs, "timestamp", self.clock) or self.clock),
        )
        return offer

    def see(
        self,
        *,
        t: float,
        text: str,
        scene: str = "unknown",
        changed: bool = False,
        eyes_ok: bool = True,
        delay: bool = False,
        block: bool = False,
    ) -> None:
        """采一帧。到点就识别。识别进行时采集不停。"""
        if t < self.clock:
            t = self.clock
        self.clock = t
        if not self.eyes_on:
            self.captured_while_off += 0
            return
        self.seq += 1
        frame = _Frame(self.seq, t, changed, text, scene or "unknown")
        self.frames.append(frame)
        del self.frames[:-BUFFER]
        self._age(t)
        if self.paused:
            return
        self._pump(eyes_ok=eyes_ok, delay=delay, block=block)

    def release_held(self, *, newest_first: bool = False) -> None:
        """较早的识别较晚返回。序号已经落后的结果丢掉。"""
        late = list(self.held)
        self.held.clear()
        if newest_first:
            late.reverse()
        for job in late:
            self._apply(job)

    def user_says(self, text: str) -> dict:
        spoken = " ".join((text or "").split())
        self.epoch += 1
        self.candidate = None
        kind = "chat"
        compact = _compact(spoken)
        if any(word in compact for word in _PAUSE):
            self.speak_locked = True
            self.eyes_on = True
            kind = "pause"
        elif any(word in compact for word in _LOOK_OFF):
            self.eyes_on = False
            self.speak_locked = True
            kind = "look_off"
        elif any(word in _compact(spoken) for word in _LOOK_ON):
            self.eyes_on = True
            kind = "look_on"
        elif any(word in _compact(spoken) for word in _HUSH):
            self.speak_locked = True
            kind = "hush"
        elif any(word in _compact(spoken) for word in _TALK_ON):
            self.speak_locked = False
            kind = "talk_on"
        turn = classify_turn(spoken)
        self.turn_kind = turn
        self.situation.note_user(spoken)
        if self.situation.talk == "quiet":
            self.speak_locked = True
        elif self.situation.talk == "more" and kind not in {"pause", "look_off"}:
            self.speak_locked = False
        if not self.conversation_focus and self.screen_focus and turn != "new":
            self.conversation_focus = self.screen_focus
        if self.conversation_focus:
            if turn == "new":
                self.topic_possibilities = [self.conversation_focus, "new"]
                self.conversation_until = self.clock
                self.situation.hold_until = 0
            elif turn == "unclear":
                self.topic_possibilities = [self.conversation_focus, "screen", "new"]
                self.situation.hold_until = time.time() + 30
                self.conversation_until = self.clock + 20
            else:
                self.topic_possibilities = [self.conversation_focus]
                self.situation.hold_until = time.time() + 30
                self.conversation_until = self.clock + 20
        else:
            self.situation.hold_until = 0
            self.topic_possibilities = []
        asks_screen = any(word in spoken for word in ("画面", "屏幕", "在干嘛", "这是什么", "歌名", "报错"))
        return {
            "turn": turn,
            "chat": True,
            "kind": kind,
            "screen_answer": bool(asks_screen and self.eyes_on and self.source_valid and kind != "look_off"),
            "proactive": False,
            "epoch": self.epoch,
        }

    def end_conversation(self) -> None:
        """话题结束。不补播已经作废的评论，也不把人拽去当前画面。"""
        self.conversation_until = self.clock
        self.blocked_object = self.screen_focus
        self.conversation_focus = ""
        self.topic_possibilities = []
        self.situation.hold_until = 0
        self.situation.focus_object_id = ""
        self.candidate = None

    def finish_user_turn(self) -> str:
        """他这句说完。不补播。屏幕已经换了，也不把他拽过去。"""
        self.candidate = None
        self.situation.hold_until = 0
        screen = self.screen_focus
        talk = self.conversation_focus
        if self.turn_kind == "new" or (screen and talk and screen != talk):
            self.blocked_object = screen
            self.conversation_focus = ""
            self.topic_possibilities = []
            return "reunderstand"
        if self.turn_kind in {"continue", "reply"} and (not screen or screen == talk):
            return "resume"
        if screen and talk and screen != talk:
            self.blocked_object = screen
        return "hold"

    def pulse(self, t: float, *, eyes_ok: bool = True, gap: str = "") -> None:
        """没变、超时、缺口也要进入时间线。序号只增不减。"""
        if t < self.clock:
            t = self.clock
        self.clock = t
        self.seq += 1
        if not eyes_ok:
            self._fail()
            self.situation.watch_state = "invalid"
            self.situation.invalid_before = self.clock
            return
        if self._was_down:
            self.recovery_looks += 1
            self._was_down = False
            self.segment += 1
            self.gaps.append("眼睛恢复，故障期间没有看成")
            self.situation.unknowns = ["中间有一段没看清"]
            self.situation.invalid_before = self.clock
            self.source_valid = True
            self.eyes_down = False
            self._retry_step = 0
            self.queue.clear()
        if gap:
            self.segment += 1
            self.gaps.append(gap)
            self.situation.progress = ""
            self.situation.unknowns = ["中间有一段没看清"]
            self.situation.invalid_before = self.clock
        self._age(self.clock)

    def dsh_returns(self, epoch: int, action: str, text: str = "", topic_id: str = "") -> str | None:
        if epoch != self.epoch or self.candidate is None or self.candidate.epoch != epoch:
            self.dropped_late += 1
            self.candidate = None
            return None
        if topic_id and topic_id != self.candidate.topic_id:
            self.dropped_late += 1
            self.candidate = None
            return None
        item = self.candidate
        self.candidate = None
        self.considered[item.key] = self.clock
        if action == "silent" or not (text or "").strip() or (text or "").strip().lower() == "silent":
            self.silent_notes += 1
            return ""
        line = text.strip()
        self.speeches.append(line)
        self.conversation_focus = item.object_id
        self.topic_possibilities = [item.object_id]
        self.situation.note_offered(True)
        return line

    def cue(self) -> str:
        body = self.situation.blocks()
        if self.gaps and self.segment > 1:
            body += "\n中间有一段没看清，不把缺口两侧当成同一段情节。"
        if self.plan_standby:
            body += "\n【陪伴】长时间没有新的进展，先旁观。"
        return body[:CUE_CAP]

    def _pump(self, *, eyes_ok: bool, delay: bool, block: bool) -> None:
        if self.inflight is not None:
            self._enqueue(force=False)
            return
        if self.eyes_down and self.clock < self._retry_at:
            return
        if self.queue:
            job = self.queue.pop(0)
        else:
            job = self._enqueue(force=True)
        if job is None:
            return
        if not eyes_ok:
            self._fail()
            return
        recovered = self._was_down
        if recovered:
            self.recovery_looks += 1
            self._was_down = False
            self.segment += 1
            self.gaps.append("眼睛恢复，故障期间没有看成")
            self.situation.unknowns = ["中间有一段没看清"]
            self.queue.clear()
        self.source_valid = True
        self.eyes_down = False
        self._retry_step = 0
        if block:
            self.inflight = job
            return
        if delay:
            self.held.append(job)
            self._mark(job)
            return
        self._finish(job)

    def release_inflight(self) -> None:
        job = self.inflight
        if job is None:
            return
        self._finish(job)

    def _mark(self, job: _Job) -> None:
        self.looks += 1
        if job.forced:
            self.forced_looks += 1
        self.last_look_at = self.clock
        self.last_window_end = job.seq_end
        self.windows.append((job.seq_start, job.seq_end))

    def _finish(self, job: _Job) -> None:
        self.inflight = None
        self._mark(job)
        self._apply(job)

    def _enqueue(self, *, force: bool) -> _Job | None:
        if not self.frames:
            return None
        scene = self.frames[-1].scene
        changed = any(frame.changed and frame.t > self.last_look_at for frame in self.frames)
        due_change = changed and (self.clock - self.last_look_at) >= COALESCE
        due_interval = (self.clock - self.last_look_at) >= INTERVALS.get(scene, 10.0)
        if not due_change and not due_interval:
            return None
        if not force:
            if len(self.queue) >= QUEUE_CAP:
                self.coalesced += 1
                return None
            if self.queue and (self.clock - self.queue[-1].t) < COALESCE and not due_interval:
                self.coalesced += 1
                return None
        elif self.inflight is not None:
            return None
        start = max(1, self.last_window_end - OVERLAP + 1) if self.last_window_end else self.frames[0].seq
        window = [frame for frame in self.frames if frame.seq >= start]
        if not window:
            window = self.frames[-1:]
        if self.applied_through and window[0].seq > self.applied_through + 1:
            self.segment += 1
            self.gaps.append(f"缓冲之外 {self.applied_through + 1}-{window[0].seq - 1}")
            self.situation.unknowns = ["中间有一段没看清"]
            self.situation.progress = ""
        job = _Job(
            seq_end=window[-1].seq,
            seq_start=window[0].seq,
            t=window[-1].t,
            text=window[-1].text,
            scene=window[-1].scene,
            changed=any(frame.changed for frame in window),
            forced=due_interval and not due_change,
        )
        if not force:
            self.queue.append(job)
            self.max_queue = max(self.max_queue, len(self.queue))
            return None
        self.max_queue = max(self.max_queue, len(self.queue) + 1)
        return job

    def _apply(self, job: _Job) -> None:
        if job.seq_end < self.applied_through:
            self.dropped_late += 1
            return
        if job.seq_end > self.applied_through + 1 and self.applied_through and job.seq_start > self.applied_through + 1:
            if not any(gap.startswith("缓冲") and str(job.seq_start) in gap for gap in self.gaps):
                self.segment += 1
                self.gaps.append(f"结果越过 {self.applied_through + 1}-{job.seq_start - 1}")
                self.situation.progress = ""
        self.applied_through = max(self.applied_through, job.seq_end)
        obs = parse_observation(job.text, timestamp=job.t)
        if obs.content_type in {"unknown", "other"} and job.scene in INTERVALS:
            obs.content_type = job.scene
        allow = (
            self.eyes_on
            and self.source_valid
            and not self.speak_locked
            and not self.plan_standby
            and self.clock >= self.conversation_until
        )
        before = self.situation.progress
        offer = self.situation.ingest(obs, allow_offer=allow)
        self.screen_focus = self.situation.latest_object_id
        progress = self.situation.progress
        key = event_key(self.situation.scene, self.situation.latest_object_id, obs.visible_text or obs.visible_events, progress)
        already = bool(self.events.get(key, {}).get("open"))
        if progress and progress != before and not already:
            self.last_progress = progress
            self.last_progress_at = self.clock
            self.plan_standby = False
        self._touch_event(key, job.t, self.situation.latest_object_id)
        self._remember(job, key)
        if already or (key in self.considered and self.events.get(key, {}).get("open")):
            return
        if offer is not None and offer.object_id == self.blocked_object:
            return
        if offer is not None and self.blocked_object and offer.object_id != self.blocked_object:
            self.blocked_object = ""
        if offer is None or self.candidate is not None:
            return
        if self.situation.topic_id == self.situation.last_offered_topic:
            return
        self.n_offers += 1
        self.candidate = Candidate(
            epoch=self.epoch,
            summary=offer.summary,
            topic_id=offer.topic_id,
            object_id=offer.object_id,
            key=key,
            observation_time=job.t,
        )
        self.inflight_epoch = self.epoch

    def _touch_event(self, key: str, t: float, object_id: str) -> None:
        current = self.events.get(key)
        if current and current["open"]:
            current["last_seen"] = t
        else:
            self.events[key] = {
                "first_seen": t,
                "last_seen": t,
                "open": True,
                "object_id": object_id,
            }
        for other, item in self.events.items():
            if other != key and item["open"] and item["object_id"] == object_id:
                item["open"] = False
                self.considered.pop(other, None)

    def _remember(self, job: _Job, key: str) -> None:
        self.log.append({
            "segment": self.segment,
            "seq": job.seq_end,
            "t": job.t,
            "text": job.text,
            "key": key,
        })
        extra = len(self.log) - LOG_CAP
        if extra > 0:
            del self.log[:extra]
            self.archived += extra

    def _age(self, t: float) -> None:
        if self.last_progress and (t - self.last_progress_at) >= PLAN_IDLE:
            self.plan_standby = True
        if not self.source_valid:
            self.situation.watch_state = "invalid"
        elif self.last_progress and (t - self.last_progress_at) >= 30:
            self.situation.watch_state = "stalled"
        else:
            self.situation.watch_state = "fresh"
        closed = [
            key for key, item in self.considered.items()
            if not self.events.get(key, {}).get("open") and (t - item) >= CONSIDER_AGE
        ]
        for key in closed:
            self.considered.pop(key, None)
        if self.conversation_focus and t >= self.conversation_until and self.situation.hold_until:
            self.situation.hold_until = 0

    def _fail(self) -> None:
        self.failed_attempts += 1
        self.eyes_down = True
        self.source_valid = False
        self._was_down = True
        wait = BACKOFF[min(self._retry_step, len(BACKOFF) - 1)]
        self._retry_step += 1
        self._retry_at = self.clock + wait
        self.retry_after = time.monotonic() + wait
        self.candidate = None
