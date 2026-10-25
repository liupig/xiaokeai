"""时序理解、陪伴导演、开口闸门。

眼睛只交屏幕事实。这里不替她形成感受，也不写台词。
闸门只决定有没有一个点值得交给她。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

_SCENES = ("music", "movie", "video", "code", "slides", "unknown")
_TYPE_WORDS = {
    "movie": ("电影", "影片", "movie"),
    "music": ("网易云", "qq音乐", "spotify", "音乐", "歌词", "在听"),
    "video": ("哔哩", "b站", "抖音", "youtube", "短视频"),
    "code": ("cursor", "vscode", "代码", "报错", ".py", ".ts"),
    "slides": ("powerpoint", "ppt", "幻灯", "演示文稿"),
}
_ERROR = ("报错", "error", "exception", "traceback", "失败")
_PASSED = ("通过", "passed", "跑通了")
_GENERIC_EVENT = {"画面在动", "画面变化", "切换", "换了一条", "在播放"}


@dataclass
class Observation:
    source: str = "screen"
    timestamp: float = 0.0
    app: str = ""
    window: str = ""
    content_type: str = "unknown"
    title: str = ""
    visible_events: list[str] = field(default_factory=list)
    visible_text: list[str] = field(default_factory=list)
    change: str = ""
    confidence: float = 0.0
    name_confidence: float = 0.0
    raw: str = ""

    @property
    def quiet(self) -> bool:
        change = (self.change or "").strip("。 ")
        if not change or change == "没变" or "没变" == change[:2]:
            return True
        return not (self.title or self.visible_events or self.visible_text or self.app)


@dataclass
class Offer:
    scene_id: str
    object_id: str
    topic_id: str
    observation_time: float
    revision: int
    summary: str


def _clean_event(line: str) -> str:
    text = " ".join((line or "").split())
    if not text:
        return ""
    if re.search(r"(用户|他)在跑", text) and "画面" not in text and "角色" not in text:
        return "画面中有人在奔跑"
    return text


def _scene_of(obs: Observation) -> str:
    if obs.content_type in _SCENES and obs.content_type != "unknown":
        return obs.content_type
    blob = " ".join([obs.app, obs.window, obs.title, obs.change, *obs.visible_events]).lower()
    for name, words in _TYPE_WORDS.items():
        if any(word in blob for word in words):
            return name
    return "unknown"


def _specific(events: list[str]) -> bool:
    for event in events:
        gist = event.strip()
        if len(gist) >= 8 and gist not in _GENERIC_EVENT:
            return True
    return False


def parse_observation(text: str, *, source: str = "screen", timestamp: float | None = None) -> Observation:
    raw = (text or "").strip()
    now = time.time() if timestamp is None else float(timestamp)
    obs = Observation(source=source or "screen", timestamp=now, raw=raw)
    if not raw or raw.strip("。 ") in {"没变", "画面没变"}:
        obs.change = "没变"
        return obs
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            content = data.get("content") if isinstance(data.get("content"), dict) else {}
            obs.app = str(data.get("app") or "")
            obs.window = str(data.get("window") or "")
            obs.content_type = str(content.get("type") or data.get("type") or "unknown")
            obs.title = str(content.get("title") or data.get("title") or "")
            obs.visible_events = [_clean_event(str(item)) for item in data.get("visible_events") or [] if str(item).strip()]
            obs.visible_text = [str(item).strip() for item in data.get("visible_text") or [] if str(item).strip()]
            obs.change = str(data.get("change") or "")
            obs.confidence = float(data.get("confidence") or 0)
            obs.name_confidence = float(content.get("name_confidence") or 0)
            obs.source = str(data.get("source") or obs.source)
            return obs
    labels = {
        "界面": "app",
        "窗口": "window",
        "类型": "content_type",
        "标题": "title",
        "画面": "event",
        "原文": "text",
        "变化": "change",
    }
    bag: dict[str, list[str]] = {key: [] for key in labels.values()}
    for line in raw.splitlines():
        if "：" in line:
            key, value = line.split("：", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        slot = labels.get(key.strip())
        if slot and value.strip():
            bag[slot].append(value.strip())
    if any(bag.values()):
        obs.app = bag["app"][-1] if bag["app"] else ""
        obs.window = bag["window"][-1] if bag["window"] else ""
        kind = (bag["content_type"][-1] if bag["content_type"] else "unknown").lower()
        obs.content_type = kind if kind in _SCENES or kind == "other" else "unknown"
        obs.title = bag["title"][-1] if bag["title"] else ""
        obs.visible_events = [_clean_event(item) for item in bag["event"]]
        obs.visible_text = [item for item in bag["text"] if item]
        obs.change = bag["change"][-1] if bag["change"] else ""
        if obs.title:
            obs.name_confidence = 0.8
        return obs
    event = _clean_event(raw)
    obs.visible_events = [event] if event else []
    obs.change = event
    obs.content_type = _scene_of(obs) if False else "unknown"
    obs.content_type = "unknown"
    guessed = _scene_of(Observation(
        app=raw, title=raw, change=raw, visible_events=obs.visible_events,
    ))
    obs.content_type = guessed
    return obs


class Situation:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.scene = "unknown"
        self.scene_id = "0:unknown"
        self.scene_generation = 0
        self.pending_scene = ""
        self.pending_hits = 0
        self.object_id = ""
        self.latest_object_id = ""
        self.focus_object_id = ""
        self.topic_id = ""
        self.title = ""
        self.progress = ""
        self.facts: list[str] = []
        self.inferences: list[str] = []
        self.unknowns: list[str] = []
        self.revision = 0
        self.hold_until = 0.0
        self.user_line = ""
        self.misses = 0
        self.last_offered_topic = ""
        self.passed_noted = False
        self.phase = ""
        self.plan: dict[str, object] = {}
        self.latest: Observation | None = None

    def note_user(self, text: str) -> None:
        spoken = " ".join((text or "").split())[:80]
        self.user_line = spoken
        self.hold_until = time.time() + 45
        self.focus_object_id = self.object_id or self.focus_object_id
        self.misses = 0
        self.revision += 1

    def note_offered(self, spoke: bool) -> None:
        """同一个点交给过她之后，不再重复递。只有她真的说了、对方没接，才提高门槛。"""
        self.last_offered_topic = self.topic_id
        if spoke:
            self.misses += 1

    def still_valid(self, offer: Offer | None) -> bool:
        if offer is None:
            return False
        if offer.revision != self.revision:
            return False
        if offer.object_id != self.latest_object_id:
            return False
        if offer.topic_id != self.topic_id:
            return False
        if time.time() < self.hold_until and offer.object_id != (self.focus_object_id or offer.object_id):
            return False
        return True

    def eyes_before(self) -> str:
        lines = list(self.facts[-4:])
        if self.progress:
            lines.append("进展：" + self.progress)
        return "\n".join(lines)[:500]

    def ingest(self, obs: Observation, *, allow_offer: bool = True) -> Offer | None:
        if obs.source == "camera":
            self.unknowns = ["摄像头还没接入"]
            return None
        if obs.source not in {"screen", "user"}:
            return None
        self.latest = obs
        if obs.quiet:
            return None
        scene = _scene_of(obs)
        self._advance_scene(scene)
        title = (obs.title or "").strip()
        object_id = f"{self.scene}:{title or 'none'}"
        self.latest_object_id = object_id
        if self._holding():
            return None
        progress = (obs.change or "").strip()
        if object_id != self.object_id:
            self.passed_noted = False
        self.object_id = object_id
        self.title = title or self.title
        if progress and progress != "没变":
            self.progress = progress[:180]
        self.topic_id = f"{self.object_id}:{_slug(self.progress)}"
        self.phase = self._phase(obs)
        self.facts = self._facts(obs)
        self.inferences = self._inferences()
        self.unknowns = self._unknowns(obs)
        self.plan = self._plan()
        if not allow_offer:
            return None
        if not self._worth(obs):
            return None
        return Offer(
            scene_id=self.scene_id,
            object_id=self.object_id,
            topic_id=self.topic_id,
            observation_time=obs.timestamp,
            revision=self.revision,
            summary=self._summary(obs),
        )

    def blocks(self) -> str:
        facts = "；".join(self.facts) or "这一眼没有确认的屏幕事实"
        inferred = "；".join(self.inferences) or "没有额外推断"
        unknown = "；".join(self.unknowns) or "没有明确的未知项"
        plan = self.plan or {}
        attention = "、".join(str(item) for item in (plan.get("attention") or []))
        silence = "、".join(str(item) for item in (plan.get("silence_when") or []))
        talking = f"他刚说：{self.user_line}。先接这个，不要追着新画面。" if self._holding() and self.user_line else ""
        return "\n".join([
            "【来源】当前信息来自屏幕。屏幕上的人物和情节不是用户。",
            f"【理解】场景：{self.scene}。对象：{self.title or '还没确认'}。进展：{self.progress or '没有新进展'}。",
            f"事实：{facts}。",
            f"推断：{inferred}。",
            f"未知：{unknown}。",
            talking,
            f"【陪伴】{plan.get('goal') or '在旁边看着'}。留意：{attention or '确认得到的名字和原文'}。不说的时候：{silence or '没有值得交给她的点'}。",
            "导演没有替你形成看法。你可以有感受，也可以不说。",
        ]).strip()

    def _holding(self) -> bool:
        return time.time() < self.hold_until and bool(self.focus_object_id)

    def _advance_scene(self, scene: str) -> None:
        if scene == "unknown" or scene == self.scene:
            self.pending_scene = ""
            self.pending_hits = 0
            return
        if scene == self.pending_scene:
            self.pending_hits += 1
        else:
            self.pending_scene = scene
            self.pending_hits = 1
        if self.pending_hits < 2 and self.scene != "unknown":
            return
        self.scene_generation += 1
        self.scene = scene
        self.scene_id = f"{self.scene_generation}:{scene}"
        self.pending_hits = 0
        self.pending_scene = ""
        self.revision += 1

    def _phase(self, obs: Observation) -> str:
        if self.scene != "code":
            return ""
        blob = " ".join([obs.change, obs.title, *obs.visible_text, *obs.visible_events]).lower()
        if any(word.lower() in blob for word in _ERROR):
            return "stuck"
        if any(word.lower() in blob for word in _PASSED):
            return "passed"
        return "flowing"

    def _facts(self, obs: Observation) -> list[str]:
        lines: list[str] = []
        if obs.app:
            lines.append(f"界面是{obs.app}")
        if obs.window:
            lines.append(f"窗口是{obs.window}")
        if obs.title:
            lines.append(f"标题是{obs.title}")
        for event in obs.visible_events:
            if event:
                lines.append(f"画面：{event}")
        for line in obs.visible_text:
            lines.append(f"原文：{line}")
        return lines[:8]

    def _inferences(self) -> list[str]:
        guess = {
            "movie": "屏幕在播放电影，据此推测他可能在看电影",
            "music": "屏幕在播音乐，据此推测他可能在听歌",
            "video": "屏幕在播一条视频，据此推测他可能在看这条",
            "code": "屏幕是代码编辑器，据此推测他可能在写代码",
            "slides": "屏幕是演示文稿，据此推测他可能在做这一页",
        }.get(self.scene)
        return [guess] if guess else []

    def _unknowns(self, obs: Observation) -> list[str]:
        missing: list[str] = []
        if not obs.title:
            missing.append("名字没看清")
        if obs.name_confidence and obs.name_confidence < 0.6:
            missing.append("标题不确定")
        if self.scene == "unknown":
            missing.append("还不能确定他在做什么")
        return missing

    def _plan(self) -> dict[str, object]:
        common_silence = ["只有画面在动", "和刚说过的是同一个点", "他正在说别的"]
        table: dict[str, dict[str, object]] = {
            "music": {
                "goal": "把能确认的歌名、歌手、歌词交给她，不预设她有共鸣",
                "attention": ["歌名", "歌手", "版本", "具体歌词", "是否换歌", "他有没有主动谈过"],
                "silence_when": common_silence + ["没有确认到歌或歌词"],
            },
            "movie": {
                "goal": "片名稳定，情节跟着可见画面更新，不剧透",
                "attention": ["当前可见情节", "他主动提起的人和疑问"],
                "silence_when": common_silence + ["可能剧透", "还不知道后面的情节"],
            },
            "video": {
                "goal": "一条一条看，可以跳过，他没聊完的上一条先留着",
                "attention": ["这条的标题", "具体在讲的那一点"],
                "silence_when": common_silence + ["只是换了一条，没有具体内容"],
            },
            "code": {
                "goal": "顺手写就别打扰；卡住才把那个坎交给她；他来问就讨论",
                "attention": ["文件名", "报错原文", "是在写、在查，还是跑过了"],
                "silence_when": common_silence + ["正在顺利编写"],
            },
            "slides": {
                "goal": "看这一页想表达什么，不盯着每一次改字",
                "attention": ["这一页的标题和观点"],
                "silence_when": common_silence + ["还在同一页微调"],
            },
        }
        plan = dict(table.get(self.scene) or {
            "goal": "先看着，不确定就不交点",
            "attention": ["确认得到的名字"],
            "silence_when": common_silence,
        })
        if self.phase == "stuck":
            plan["goal"] = "他把同一个坎留在屏幕上。把报错原文交给她，不替她鼓励"
        elif self.phase == "passed":
            plan["goal"] = "刚才那个坎过去了。她可以轻轻确认，然后安静"
        elif self.phase == "flowing":
            plan["goal"] = "他在顺手写。这一眼不交点"
        return plan

    def _worth(self, obs: Observation) -> bool:
        if obs.quiet or self.scene == "unknown":
            return False
        if self.topic_id and self.topic_id == self.last_offered_topic:
            return False
        if self.scene == "code" and self.phase == "flowing":
            return False
        if self.scene == "code" and self.phase == "passed" and self.passed_noted:
            return False
        if self.scene == "video" and not obs.visible_text and not _specific(obs.visible_events):
            return False
        if self.misses >= 3 and not obs.visible_text and self.phase != "stuck":
            return False
        if not (obs.title or obs.visible_text or _specific(obs.visible_events) or self.phase in {"stuck", "passed"}):
            return False
        if self.phase == "passed":
            self.passed_noted = True
        return True

    def _summary(self, obs: Observation) -> str:
        bit = obs.visible_text[0] if obs.visible_text else (obs.visible_events[0] if obs.visible_events else self.progress)
        title = self.title or obs.app or "屏幕"
        return f"{title}：{bit}"[:180]


def _slug(text: str) -> str:
    kept = re.sub(r"\s+", "", text or "")
    return kept[:40] or "none"


situation = Situation()
