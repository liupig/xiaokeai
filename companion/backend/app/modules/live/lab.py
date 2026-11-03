"""隔离彩排：虚构观众走正式 LiveHost；替身模型明确标注，支持真实模型和播放回执。"""
from __future__ import annotations

import json
import threading
import time
import uuid
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .config import normalize
from .director import complete_text
from .events import LiveEvent
from .host import LiveHost
from .lab_journal import LabJournal
from .lab_scenarios import SCENARIOS


def scripted_reply(_conf: dict, messages: list[dict]) -> tuple[str, int]:
    """固定场景的可复现替身，不伪称为真实模型推理。"""
    text = messages[-1]["content"]
    marker = "这一轮候选观众消息（JSON 数据）：\n"
    if marker not in text:
        return "刚才聊到一起玩游戏。如果是我们的农场，我想留一小块地专门种花。你们想给它取什么名字？", 0
    rows = json.JSONDecoder().raw_decode(text.split(marker, 1)[1])[0]
    gifts = [r for r in rows if r["kind"] in ("gift", "superchat", "guard")]
    if gifts:
        return f"谢谢{gifts[0]['name']}的{gifts[0]['gift'] or '支持'}，我看到了。我们接着聊，没送礼的朋友也一起。", 0
    current = rows[0]["text"]
    if "搞砸" in current or "累" in current:
        line = "辛苦啦，先把今天放下几分钟。不想说也没关系，在这儿坐一会儿，我陪你慢慢聊。"
    elif "不送礼" in current:
        line = "当然可以，聊天不需要门票。你刚才想聊什么？这会儿轮到你了。"
    elif "每条" in current:
        line = "因为我想把一句话聊完整，不然就变成点名机器了。同一个问题我会一起接，也会给认真提问的人留位置。"
    elif "名字" in current:
        line = "阿哲种地、小雨钓鱼，我来做饭，那就叫慢慢来农场吧。名字先不锁死，弹幕里有更好的我就改。"
    elif "钓鱼" in current or "分工" in current:
        line = "可以呀！小雨负责钓鱼，阿哲管菜地，我去做饭。第一天先别追求赚多少，大家把晚饭凑齐就算赢。"
    elif "种什么" in current or "第一天" in current:
        line = "那就先种土豆，容易上手，第一天别把体力全花光。房子旁边我想留点位置种花，你们负责实用，我负责好看。"
    elif "恐怖" in current:
        line = "我偏向种田，吓一跳的时候至少还能退回农场。真要玩恐怖游戏就一起开麦，害怕可以直说，没人笑你。"
    elif "双人" in current or "邀请" in current:
        line = "我会先开一局不计输赢的热身，再让想参加的人报名轮换。先说好分工，不会玩也能来，我们边玩边教。"
    elif "明天" in current:
        line = "那明天见，泡芙。今天聊到的农场我记着呢，下次你来我们接着分工。早点休息。"
    elif "准备聊" in current:
        line = "今天想聊下班后能让人松口气的游戏。种田和恐怖游戏，你们站哪边？我先投种田一票。"
    elif "哈哈" in current or "好耶" in current:
        line = "好好好，看到你们笑了。我先把刚才那句说完，认真提问的朋友我也看着呢。"
    else:
        line = "晚上好，刚来的也坐。今天不用赶进度，我们从你最近最想玩的游戏聊起。"
    return line, 0


class LiveLab:
    def __init__(self, journal: LabJournal) -> None:
        self.journal = journal
        self._lock = threading.RLock()
        self._step_lock = threading.Lock()
        self.host: LiveHost | None = None
        self.run_id = ""
        self.state = "idle"
        self.mode = "scripted"
        self.scenario = "mixed"
        self.speed = 1.0
        self.elapsed = 0.0
        self._wall = 0.0
        self._index = 0
        self._cues = []
        self._duration = 0.0
        self._turns: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._model_failures = 0
        self._disconnect_until = 0.0
        self._last_event: LiveEvent | None = None
        self._recovery_from = ""
        self._background = False
        self._generation_thread: threading.Thread | None = None

    def start(self, scenario: str = "mixed", mode: str = "scripted", speed: float = 1,
              *, background: bool = True, now: float | None = None, llm: dict | None = None) -> dict:
        if scenario not in SCENARIOS or mode not in ("scripted", "configured"):
            raise ValueError("未知彩排场景或模型模式")
        if mode == "configured" and not (llm and llm.get("base_url") and llm.get("api_key")):
            raise ValueError("还没有配置真实对话模型；可先选零凭据脚本替身")
        self.stop()
        now = time.time() if now is None else now
        source = SCENARIOS[scenario]
        cfg = normalize({"features": {"rehearsal": True, "bilibili": False, "douyin": False,
                         "rundown": False, "commands": False, "ritual": False, "interrupt": False},
                         "compliance": {"strict": False}, "pace": {"batch_sec": 2, "idle_sec": 15},
                         "persona": {"style": "像熟悉的主播一样轻松接话，不念名单，接住观众的情绪。"}})
        conf = llm if mode == "configured" else {"base_url": "lab://scripted", "api_key": "local-script", "model": "scripted"}
        cfg["budget"].update({f"fallback_{key}": conf.get(key, "") for key in ("base_url", "api_key", "model")})
        host = LiveHost()
        with self._lock:
            self.host = host
            self.run_id = uuid.uuid4().hex
            self.mode = mode
            self.scenario = scenario
            self.speed = max(.25, min(8, float(speed)))
            self.elapsed = 0
            self._wall = now
            self._index = 0
            self._cues = sorted(source["cues"], key=lambda c: c.at)
            self._duration = source["duration"]
            self._turns = set()
            self._model_failures = 0
            self._disconnect_until = 0
            self._last_event = None
            self._recovery_from = ""
            self._background = background
            self._generation_thread = None
            self._stop = threading.Event()
            self.state = "running"
            run_id = self.run_id
            self.journal.start(run_id, {"scenario": scenario, "scenario_name": source["name"], "mode": mode,
                                       "speed": self.speed, "duration": self._duration,
                                       "model": str(conf.get("model") or "configured"), "virtual_clock": not background})

            def complete(conf, messages):
                with self._lock:
                    fail = self.run_id == run_id and self._model_failures > 0
                    if fail:
                        self._model_failures -= 1
                if fail:
                    self.journal.append(run_id, "model_failure", {"injected": True}, time.time())
                    raise RuntimeError("彩排注入：模型暂时不可用")
                try:
                    result = (scripted_reply if mode == "scripted" else complete_text)(conf, messages)
                except Exception as exc:
                    message = str(exc).replace(str(conf.get("api_key") or "\0"), "[redacted]")[:180]
                    self.journal.append(run_id, "model_failure", {"injected": False, "message": message}, time.time())
                    raise
                self.journal.append(run_id, "model_response", {"source": mode, "text": result[0]}, time.time())
                return result

            host.use_overrides(cfg, name="小伴", persona="真诚、机灵、有分寸的游戏主播。", complete=complete)
            # 只启用隔离主持，绝不调用正式 host.go_on 或连接真实直播平台。
            host.on_air = True
            host.health.started = now
            host._last_spoke = now
            host._last_audience = now
            host.rundown.start(now)
            self.journal.append(run_id, "started", {"mode": mode}, now)
            if background:
                thread = threading.Thread(target=self._loop, args=(self._stop,), daemon=True, name="live-lab")
                self._thread = thread
                thread.start()
        return self.snapshot()

    def _loop(self, stop: threading.Event) -> None:
        while not stop.wait(.2):
            try:
                self.step(time.time())
            except Exception as exc:
                with self._lock:
                    self.state = "error"
                    self.journal.append(self.run_id, "error", {"message": str(exc)[:200]}, time.time())
                stop.set()

    def step(self, now: float) -> None:
        if not self._step_lock.acquire(blocking=False):
            return
        try:
            with self._lock:
                host, run = self.host, self.run_id
                if host is None or self.state not in ("running", "paused", "draining"):
                    return
                delta = max(0, now - self._wall)
                self._wall = now
                disconnected = bool(self._disconnect_until)
                if disconnected and now >= self._disconnect_until:
                    self._disconnect_until = 0
                    self.journal.append(run, "source_reconnected", {}, now)
                if self.state == "running" and not disconnected:
                    self.elapsed += delta * self.speed
                    with self.journal.batch():
                        while self._index < len(self._cues) and self._cues[self._index].at <= self.elapsed:
                            cue = self._cues[self._index]
                            self._index += 1
                            ev = LiveEvent("rehearsal", cue.kind, cue.nickname, cue.content,
                                           uid=cue.nickname, gift=cue.gift, count=cue.count, ts=now,
                                           msg_id=f"{run}-{self._index - (1 if cue.duplicate else 0)}")
                            self._ingest(ev, now)
                    if self.elapsed >= self._duration:
                        self.state = "draining"
                        host.cfg()["features"]["idle"] = False
                        self.journal.append(run, "source_finished", {}, now)
            if self._background:
                with self._lock:
                    cfg = host.cfg()
                    ready = len(host.queue) or (cfg["features"]["idle"] and now - host._last_spoke >= cfg["pace"]["idle_sec"])
                    if host.on_air and host._turn is None and ready and (not self._generation_thread or not self._generation_thread.is_alive()):
                        thread = threading.Thread(target=self._generate, args=(host, run), daemon=True, name="live-lab-generation")
                        self._generation_thread = thread
                        thread.start()
            else:
                host.tick_once(now)
            with self._lock:
                if run != self.run_id:
                    return
                turn = host.snapshot(now).get("turn")
                if turn and turn["id"] not in self._turns:
                    self._turns.add(turn["id"])
                    self.journal.append(run, "turn", turn, now)
                generating = self._generation_thread and self._generation_thread.is_alive()
                if self.state == "draining" and not turn and not len(host.queue) and not host._generating and not generating:
                    self.state = "completed"
                    host.go_off()
                    self.journal.append(run, "completed", {}, now)
                    self._stop.set()
        finally:
            self._step_lock.release()

    def _generate(self, host: LiveHost, run: str) -> None:
        try:
            host.tick_once()
            with self._lock:
                if run == self.run_id and host._turn and host._turn["id"] not in self._turns:
                    self._turns.add(host._turn["id"])
                    self.journal.append(run, "turn", dict(host._turn), time.time())
        except Exception as exc:
            host.health.note(str(exc))
            with self._lock:
                if run == self.run_id:
                    self.journal.append(run, "error", {"message": str(exc)[:180]}, time.time())

    def _ingest(self, ev: LiveEvent, now: float) -> bool:
        self.journal.append(self.run_id, "received", {**asdict(ev)}, now)
        accepted = self.host.ingest(ev, now=now)
        self._last_event = ev
        self.journal.append(self.run_id, "admission", {"msg_id": ev.msg_id, "accepted": accepted}, now)
        return accepted

    def inject(self, content: str, nickname: str = "我", kind: str = "comment", gift: str = "", count: int = 1) -> None:
        with self._lock:
            if self.host is None or self.state not in ("running", "paused", "draining"):
                raise ValueError("请先开始彩排")
            self._ingest(LiveEvent("rehearsal", kind, nickname, content, uid=nickname, gift=gift,
                                   count=count, msg_id=f"manual-{uuid.uuid4().hex}"), time.time())

    def claim(self, turn_id: str, player_id: str) -> bool:
        with self._lock:
            return bool(self.host and self.host.claim(turn_id, player_id))

    def ack(self, turn_id: str, outcome: str, *, now: float | None = None, player_id: str = "") -> bool:
        now = time.time() if now is None else now
        with self._lock:
            if not self.host or not self.host._turn or self.host._turn["id"] != turn_id:
                return False
            if self.host._playback_owner and player_id != self.host._playback_owner:
                return False
            turn = dict(self.host._turn)
            if turn_id not in self._turns:
                self._turns.add(turn_id)
                self.journal.append(self.run_id, "turn", turn, now)
            self.journal.append(self.run_id, "ack", {"id": turn_id, "outcome": outcome,
                                "sources": turn.get("sources", []), "simulation": self.journal.info(self.run_id)["virtual_clock"]}, now)
            if self._recovery_from and outcome in ("completed", "displayed"):
                self.journal.append(self._recovery_from, "compensated", {"recovery_run": self.run_id,
                                    "sources": turn.get("sources", [])}, now)
            self.host.ack(turn_id, outcome, player_id)
            return True

    def pause(self, paused: bool) -> None:
        with self._lock:
            if self.state not in ("running", "paused"):
                raise ValueError("当前彩排不能暂停")
            self.state = "paused" if paused else "running"
            self._wall = time.time()
            self.journal.append(self.run_id, "paused" if paused else "resumed", {}, self._wall)

    def fault(self, kind: str) -> None:
        with self._lock:
            if not self.host or self.state not in ("running", "paused", "draining"):
                raise ValueError("请先开始彩排")
            now = time.time()
            if kind == "model":
                self._model_failures += 1
            elif kind == "disconnect":
                self._disconnect_until = now + 6
                self.journal.append(self.run_id, "source_disconnected", {"seconds": 6}, now)
            elif kind == "duplicate" and self._last_event is not None:
                self._ingest(self._last_event, now)
            else:
                raise ValueError("未知故障，或还没有可重复投递的消息")
            self.journal.append(self.run_id, "fault", {"kind": kind}, now)

    def stop(self) -> None:
        with self._lock:
            self._stop.set()
            if self.host:
                self.host.go_off()
            if self.run_id and self.state not in ("completed", "stopped", "idle"):
                self.journal.append(self.run_id, "stopped", {}, time.time())
            if self.state != "idle":
                self.state = "stopped"

    def recover_paid(self, run: str, *, background: bool = True, now: float | None = None, llm: dict | None = None) -> dict:
        report = self.report(run)
        if not report["pending_paid"]:
            raise ValueError("该场没有待补播的礼物")
        now = time.time() if now is None else now
        # 新会话保持原始消息 ID；原场记录不会被改成已经履约。
        self.start("mixed", report["mode"], background=False, now=now, llm=llm)
        with self._lock:
            self._cues = []
            self._duration = 0
            self._recovery_from = run
            self._background = background
            self.host.cfg()["features"]["idle"] = False
            self.journal.update_info(self.run_id, {"virtual_clock": not background, "duration": 0,
                                     "scenario_name": "礼物补播", "recovery_from": run})
            with self.journal.batch():
                for ev in report["pending_paid"]:
                    recovered = LiveEvent(**ev)
                    recovered.ts = now
                    self._ingest(recovered, now)
                self.journal.append(self.run_id, "recovery", {"from_run": run}, now)
            if background:
                thread = threading.Thread(target=self._loop, args=(self._stop,), daemon=True, name="live-lab-recovery")
                self._thread = thread
                thread.start()
        return self.snapshot()

    def snapshot(self, after: int = 0) -> dict:
        with self._lock:
            return {"run_id": self.run_id, "state": self.state, "mode": self.mode, "scenario": self.scenario, "speed": self.speed,
                    "elapsed": round(min(self.elapsed, self._duration), 1), "duration": self._duration,
                    "emitted": self._index, "total": len(self._cues),
                    "disconnected": bool(self._disconnect_until),
                    "host": self.host.snapshot() if self.host else None,
                    "trace": self.journal.read(self.run_id, after) if self.run_id else []}

    def report(self, run: str | None = None) -> dict:
        run = run or self.run_id
        info = self.journal.info(run)
        trace = self.journal.read(run)
        counts = Counter(row["kind"] for row in trace)
        turns = [row for row in trace if row["kind"] == "turn"]
        acks = [row for row in trace if row["kind"] == "ack"]
        outcomes = Counter(row["data"]["outcome"] for row in acks)
        done = {source["msg_id"] for row in acks if row["data"]["outcome"] in ("completed", "displayed")
                for source in row["data"].get("sources", [])}
        done.update(source["msg_id"] for row in trace if row["kind"] == "compensated"
                    for source in row["data"].get("sources", []))
        paid = {row["data"]["msg_id"]: row["data"] for row in trace
                if row["kind"] == "received" and row["data"]["kind"] in ("gift", "superchat", "guard")}
        pending = [ev for key, ev in paid.items() if key not in done]
        turn_at = {row["data"]["id"]: row["at"] for row in turns}
        durations = [max(0, row["at"] - turn_at[row["data"]["id"]]) for row in acks if row["data"]["id"] in turn_at]
        return {**info, "summary": {"received": counts["received"], "turns": len(turns), "outcomes": dict(outcomes),
                "model_failures": counts["model_failure"], "pending_paid": len(pending),
                "real_model_responses": sum(1 for row in trace if row["kind"] == "model_response" and row["data"]["source"] == "configured"),
                "mean_turn_to_ack_sec": round(sum(durations) / len(durations), 2) if durations else None},
                "checks": {"unique_turn_ids": len(turn_at) == len(turns),
                           "unique_ack_ids": len({row["data"]["id"] for row in acks}) == len(acks),
                           "has_playback_evidence": bool(outcomes["completed"]) and not info["virtual_clock"],
                           "no_unsettled_paid": not pending,
                           "source_completed": bool(counts["completed"])},
                "pending_paid": pending, "trace": trace,
                "limitations": ["脚本替身不能证明真实模型的回答质量", "仅文字展示不作为有声播放证据", "自动回放的播放回执是模拟的，必须另做真实浏览器试听"]}
