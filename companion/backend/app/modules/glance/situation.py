"""时序理解、陪伴导演、开口闸门。

眼睛只交屏幕事实。这里不替她形成感受，也不写台词。
闸门只决定有没有一个点值得交给她。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

_SCENES = ("music", "movie", "video", "code", "slides", "game", "unknown")
_TYPE_WORDS = {
    "movie": ("电影", "影片", "movie"),
    "music": ("网易云", "qq音乐", "spotify", "音乐", "歌词", "在听"),
    "video": ("哔哩", "b站", "抖音", "youtube", "短视频"),
    "code": ("cursor", "vscode", "代码", "报错", ".py", ".ts"),
    "slides": ("powerpoint", "ppt", "幻灯", "演示文稿"),
    "game": ("steam", "游戏", "原神", "对局"),
}
_ERROR = ("报错", "error", "exception", "traceback", "失败")
_PASSED = ("通过", "passed", "跑通了")
_GENERIC_EVENT = {"画面在动", "画面变化", "切换", "换了一条", "在播放"}
_VIDEO_HOST = ("youtube", "bilibili", "哔哩", "b站", "抖音", "快手")
_NONE_FACT = re.compile(
    r"^(unknown|none|n/?a|no|no new( facts| fact| change)?|nothing|"
    r"空|无|没有|没变|无新变化|无新事实|没有新变化|没有新事实|"
    r"视频正在播放|video playing|正在播放|出现)$",
    re.I,
)
_SELF_VIEW = re.compile(
    r"pink cartoon|cartoon character|humanoid|anime|动漫|二次元|蓝发|粉色角色|中间的角色",
    re.I,
)
_CHROME_TITLE = re.compile(
    r"^(youtube( ?页面| ?page| ?界面)?|视频播放界面|电影播放界面|电影页面|"
    r"电脑屏幕|video interface|video playback interface|playback interface|"
    r"browser|浏览器|web browser|播放界面|网站界面|website interface|screen)$",
    re.I,
)


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
    observation_id: str = ""
    artist: str = ""
    version: str = ""
    stage: str = ""
    raw: str = ""
    channel: str = ""

    @property
    def quiet(self) -> bool:
        """没有标题、原文或情节，就不构成一眼。空的「变化」不能把已经看见的事实清掉。"""
        return not (self.title or self.visible_events or self.visible_text)


@dataclass
class Offer:
    scene_id: str
    object_id: str
    topic_id: str
    observation_time: float
    revision: int
    summary: str
    channel: str = ""


def _none_fact(text: str) -> bool:
    raw = (text or "").strip(" 。.：:，,")
    if len(raw) < 2:
        return True
    return _NONE_FACT.match(raw) is not None


def _is_self(text: str) -> bool:
    return _SELF_VIEW.search(text or "") is not None


_LAYOUT = (
    "左侧", "右侧", "中间", "上方", "下方", "列表", "条目", "多个", "原图",
    "半秒", "间隔", "背景", "窗口", "界面", "屏幕", "包含", "多张", "一张",
)


def _layout_only(text: str) -> bool:
    """只是在说界面怎么摆，没有名字、数字或原文。"""
    if re.search(r"[A-Za-z]{3,}|\d", text or ""):
        return False
    compact = text or ""
    hit = False
    for word in _LAYOUT:
        if word in compact:
            compact = compact.replace(word, "")
            hit = True
    if not hit:
        return False
    compact = re.sub(r"[^\u4e00-\u9fff]", "", compact)
    return len(compact) < 4


_QUOTE = re.compile(r"[\"“「『]([^\"”」』]{2,40})[\"”」』]")
_FRAME_COUNT = re.compile(r"(一共)?\d+\s*张|多张原图|间隔半秒|间隔大约")
_POSITION = re.compile(r"(左侧|右侧|左边|右边|中间).{0,24}(人物|男性|女性|男生|女生|角色|人)")
_CHROME_BIT = re.compile(
    r"^(视频播放(窗口|界面)?|播放界面|评论区|代码(编辑器|窗口|内容|文本)?|"
    r"互动数据.*|电脑屏幕|推荐)$",
    re.I,
)
_CHROME_HAS = re.compile(
    r"视频播放|播放窗口|评论区|代码编辑|代码窗口|代码内容|代码文本|互动数据|"
    r"duoyin\.com|recommend=|点赞|点量|播放量|分享量|评论量|原图|半秒",
    re.I,
)
_STATS = re.compile(r"点赞|评论数|分享量|播放量|点量|\d+(\.\d+)?\s*万")
_SCENERY = re.compile(r"^(沙漠|田野|室内|室外|货架)(场景|里|中)?$")
_FAKE_TITLE = re.compile(r"^第\d+条$")
_LABELS = re.compile(
    r"(界面|窗口|类型|标题|画面|原文|变化|进展|歌手|版本|阶段)\s*[是为:：]"
)


def _quotes(text: str) -> list[str]:
    found = [item.strip() for item in _QUOTE.findall(text or "") if item.strip()]
    if found:
        return found
    opened = re.findall(r"[\"“「『]([^\"”」』\n]{2,40})", text or "")
    return [item.strip() for item in opened if item.strip()]


_DEAD = re.compile(
    r"^(unknown|not visible|nothing new|no new|none|n/?a|"
    r"无|没有新变化|未变|没变|解释|哈哈|未知|无新变化|无新事实)$",
    re.I,
)


def _dead(text: str) -> bool:
    raw = " ".join((text or "").split())
    if not raw or _DEAD.match(raw):
        return True
    parts = [part for part in re.split(r"[、,，/]+", raw) if part.strip()]
    return len(parts) > 1 and all(_DEAD.match(part.strip()) or _none_fact(part.strip()) for part in parts)


def _caption(text: str) -> bool:
    """复述摆放、张数、播放器外壳。这些不能当陪看的点。"""
    raw = " ".join((text or "").split())
    if not raw or _FAKE_TITLE.match(raw) or _dead(raw):
        return True
    if re.search(r"\b(man|woman|shirt|microphone|split view)\b", raw, re.I):
        return True
    if re.search(r"视频列表|四格|多段内容|缩略图|衣服颜色|户外场景|室内场景", raw):
        return True
    if re.search(r"戴眼镜|男子|女子|男生|女生|男人|女人|侧脸|人物|人影", raw) and not _quotes(raw):
        return True
    if _FRAME_COUNT.search(raw) or _POSITION.search(raw) or _SCENERY.match(raw.strip("。 ")):
        return True
    if re.match(r"^(左侧|右侧|左边|右边|屏幕左|屏幕右)", raw) and not _quotes(raw):
        return True
    if re.search(r"全部评论|条评论|\(\d+\)|显示代码|播放窗口|画面切换|专注记录|调整视角", raw):
        return True
    if re.match(r"^作者[:：]", raw) or raw.startswith("@") or re.search(r"热度最高|第\d+名|换了颜色|颜色很明显|封面换|最近三天|截图记录|代码片段|代码编辑", raw):
        return True
    if _CHROME_BIT.match(raw.strip()):
        return True
    if "记录美好生活" in raw or "原样抄" in raw or "陪看记录" in raw or "聊天窗口" in raw or "浏览消息" in raw:
        return True
    if re.search(
        r"画面模糊|无人在场|静止不动|没有人和字幕|没有字幕|字幕显示|正在播放|视频播放画面|动漫角色|代码编辑|正在编写|编程代码",
        raw,
    ):
        return True
    if _quotes(raw):
        return False
    if _STATS.search(raw):
        return True
    if _CHROME_HAS.search(raw):
        residue = _CHROME_HAS.sub("", raw)
        for word in ("器", "与", "界面", "显示", "窗口", "屏幕", "编辑", "视频"):
            residue = residue.replace(word, "")
        residue = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", residue)
        return len(residue) < 4
    return False


def _real_title(text: str) -> str:
    quotes = [quote for quote in _quotes(text) if quote and not _caption(quote)]
    if quotes:
        return max(quotes, key=len)
    raw = _keep_fact(text)
    if not raw or _caption(raw) or _FAKE_TITLE.match(raw):
        return ""
    if re.fullmatch(r"https?\S+|\S+\.(com|cn|net)\S*", raw, re.I):
        return ""
    return raw


def _keep_fact(text: str) -> str:
    raw = " ".join((text or "").split())
    if _none_fact(raw) or _is_self(raw) or _CHROME_TITLE.match(raw.strip()) or _layout_only(raw):
        return ""
    return raw


def _normalize_labels(raw: str) -> str:
    """模型有时把「标题是、画面是」写在同一行。拆回一行一项。"""
    parts = _LABELS.split(raw or "")
    if len(parts) < 3:
        return raw
    lines: list[str] = []
    pairs = parts[1:]
    for label, value in zip(pairs[0::2], pairs[1::2]):
        value = value.strip(" \n|，,。")
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines) if lines else raw


_FUNCTION = re.compile(r"[的了呢吗是不我你他她这过到就能会要还都也在把被谁哪怎么啊吧呀]")
_NAME_MARK = re.compile(r"[年记传曲歌师纪]")


def _han(text: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff]", "", text or "")


def _line(text: str) -> bool:
    """一句能接的原文，或一个像名字的标题。认不出的字就不交。"""
    raw = (text or "").strip()
    if not raw or _caption(raw) or raw in {"MSCTFIME UI", "Default IME", "Chrome Legacy Window"}:
        return False
    han = _han(raw)
    letters = re.findall(r"[A-Za-z]{2,}", raw)
    if letters and len(han) < 4:
        words = [word for word in letters if len(word) >= 3]
        return len(words) >= 2 or (len(words) == 1 and len(words[0]) >= 8)
    if _FUNCTION.search(han) and len(han) >= 4:
        return True
    return bool(4 <= len(han) <= 12 and _NAME_MARK.search(han) and not letters)


def _speakable(obs: Observation) -> str:
    """这一眼真正能交给她的那一点：一句原文，或一个具体名字。"""
    title = (obs.title or "").strip()
    for item in list(obs.visible_text) + list(obs.visible_events):
        if not item or item == title or (title and (item in title or title in item)):
            continue
        if _line(item):
            return item
    return title if _line(title) else ""


def _settle(obs: Observation) -> Observation:
    """理解层丢掉她自己、空词、摆放说明和播放器外壳。YouTube 这一类是刷视频，不是电影。"""
    obs.title = _real_title(obs.title)
    kept_events: list[str] = []
    for line in obs.visible_events:
        quotes = [quote for quote in _quotes(line) if not _caption(quote)]
        if quotes:
            kept_events.extend(quotes)
            continue
        item = _keep_fact(line)
        if item and not _caption(item):
            kept_events.append(item)
    obs.visible_events = kept_events
    kept_text: list[str] = []
    for line in obs.visible_text:
        quotes = [quote for quote in _quotes(line) if not _caption(quote)]
        if quotes:
            kept_text.extend(quotes)
            continue
        item = _keep_fact(line)
        if item and not _caption(item):
            kept_text.append(item)
    for quote in _quotes(obs.change):
        if quote and not _caption(quote) and quote not in kept_text:
            kept_text.append(quote)
    obs.visible_text = kept_text
    if _none_fact(obs.change) or _is_self(obs.change) or _caption(obs.change):
        obs.change = ""
    host = " ".join([obs.app, obs.window, obs.title, obs.raw]).lower()
    if obs.content_type in {"movie", "unknown", "other", ""} and any(word in host for word in _VIDEO_HOST):
        obs.content_type = "video"
    if obs.title:
        obs.name_confidence = obs.name_confidence or 0.8
    return obs


def _clean_event(line: str) -> str:
    text = " ".join((line or "").split())
    if not text:
        return ""
    if re.search(r"(用户|他)在跑", text) and "画面" not in text and "角色" not in text:
        return "画面中有人在奔跑"
    return text


def _kind_of(raw: str) -> str:
    """模型会写「视频」「code、video」。显式类型直接认，刷视频优先于旁边的编辑器。"""
    text = (raw or "").strip()
    low = text.lower()
    if any(word in low for word in ("video", "youtube", "bilibili")) or any(word in text for word in ("视频", "抖音", "哔哩", "快手")):
        return "video"
    if "movie" in low or "电影" in text:
        return "movie"
    if "music" in low or any(word in text for word in ("音乐", "歌词")):
        return "music"
    if "code" in low or "代码" in text:
        return "code"
    if low in _SCENES or low == "other":
        return low
    return "unknown"


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
    raw = _normalize_labels((text or "").strip())
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
            obs.observation_id = str(data.get("observation_id") or "")
            obs.artist = str(data.get("artist") or content.get("artist") or "")
            obs.version = str(data.get("version") or content.get("version") or "")
            obs.stage = str(data.get("stage") or "")
            obs.source = str(data.get("source") or obs.source)
            return _settle(obs)
    labels = {
        "界面": "app",
        "窗口": "window", "window": "window",
        "类型": "content_type", "type": "content_type",
        "标题": "title", "title": "title",
        "画面": "event",
        "原文": "text", "text": "text",
        "变化": "change", "change": "change", "进展": "change",
        "歌手": "artist",
        "版本": "version",
        "阶段": "stage",
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
        kind = bag["content_type"][-1] if bag["content_type"] else "unknown"
        obs.content_type = _kind_of(kind)
        obs.title = bag["title"][-1] if bag["title"] else ""
        obs.visible_events = [_clean_event(item) for item in bag["event"]]
        obs.visible_text = [item for item in bag["text"] if item]
        obs.change = bag["change"][-1] if bag["change"] else ""
        obs.artist = bag["artist"][-1] if bag["artist"] else ""
        obs.version = bag["version"][-1] if bag["version"] else ""
        obs.stage = bag["stage"][-1] if bag["stage"] else ""
        if obs.title:
            obs.name_confidence = 0.8
        return _settle(obs)
    event = _clean_event(raw)
    obs.visible_events = [event] if event else []
    obs.change = event
    obs.content_type = _scene_of(obs) if False else "unknown"
    obs.content_type = "unknown"
    guessed = _scene_of(Observation(
        app=raw, title=raw, change=raw, visible_events=obs.visible_events,
    ))
    obs.content_type = guessed
    return _settle(obs)


def read_steer(text: str) -> tuple[str | None, str | None]:
    """从他这句话里读出留意什么、想听多少。没提到的那项返回 None。"""
    compact = re.sub(r"\s+", "", text or "")
    talk = None
    if any(word in compact for word in ("多说点", "说多点", "多讲点", "多聊聊", "话多一点", "多说一些", "说详细点", "多说两句")):
        talk = "more"
    elif any(word in compact for word in ("别说了", "不要说", "别说话", "先别说", "安静点", "先安静", "少说点", "少说", "不用说", "别讲了")):
        talk = "quiet"
    elif any(word in compact for word in ("可以说了", "接着说", "你可以说话", "正常说")):
        talk = "normal"
    attention: str | None = None
    if any(word in compact for word in ("不用关注", "别关注", "不用留意", "别盯着", "随便看")):
        attention = ""
    else:
        found = re.search(
            r"(?:看画面里面的|看画面里的|画面里面的|画面里的|关注|留意|盯着|多看看)([^，。！？,\s]{1,16})",
            compact,
        )
        if found:
            got = re.sub(r"^(一下|一眼)", "", found.group(1))
            got = got.strip("吧啊呀呢的了")
            if got and got not in {"一下", "一眼", "这个", "那个", "什么"}:
                attention = got[:16]
    return attention, talk


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
        self.attention = ""
        self.talk = "normal"
        self.misses = 0
        self.last_offered_topic = ""
        self.video_offered_object = ""
        self.passed_noted = False
        self.phase = ""
        self.plan: dict[str, object] = {}
        self.plan_revision = 0
        self.plan_reason = ""
        self.artist = ""
        self.version = ""
        self.lyric = ""
        self.song_changed = False
        self.user_mentioned = False
        self.background: list[str] = []
        self.watch_state = "fresh"
        self.invalid_before = 0.0
        self.unread_noted = False
        self.secondary_objects: list[str] = []
        self.channel = ""
        self.latest: Observation | None = None

    def note_user(self, text: str) -> None:
        spoken = " ".join((text or "").split())[:80]
        self.user_line = spoken
        self.hold_until = time.time() + 12
        self.focus_object_id = self.object_id or self.focus_object_id
        self.misses = 0
        self.revision += 1
        if self.title and self.title in spoken:
            self.user_mentioned = True
        attention, talk = read_steer(spoken)
        if attention is not None:
            self.attention = attention
        if talk is not None:
            self.talk = talk
        if any(word in spoken for word in ("陪", "安静", "别说", "别看", "帮我", "怎么看", "先别", "关注", "留意", "多说")):
            self._replan("用户")

    def note_offered(self, spoke: bool) -> None:
        """同一个点交给过她之后，不再重复递。只有她真的说了、对方没接，才提高门槛。"""
        self.last_offered_topic = self.topic_id
        if self.scene == "video":
            self.video_offered_object = self.object_id
        if spoke:
            self.misses += 1

    def still_valid(self, offer: Offer | None) -> bool:
        if offer is None:
            return False
        if offer.revision != self.revision:
            return False
        if offer.object_id != self.latest_object_id:
            return False
        if self.invalid_before and offer.observation_time < self.invalid_before:
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
        if obs.channel:
            self.channel = obs.channel
        scene_before = self.scene
        object_before = self.object_id
        phase_before = self.phase
        scene = _scene_of(obs)
        explicit = obs.content_type in _SCENES and obs.content_type != "unknown"
        self._advance_scene(scene, explicit=explicit)
        incoming = (obs.title or "").strip()
        if self.scene != scene_before and not incoming:
            self.title = ""
        object_id = f"{self.scene}:{incoming or self.title or 'none'}"
        self.latest_object_id = object_id
        if self._holding():
            return None
        if incoming:
            self.title = incoming
        object_id = f"{self.scene}:{self.title or 'none'}"
        self.latest_object_id = object_id
        point = _speakable(obs)
        if object_id != self.object_id:
            self.passed_noted = False
            self.unread_noted = False
            self.song_changed = self.scene == "music" and bool(self.object_id)
            self.user_mentioned = False
            self.background = []
        else:
            self.song_changed = False
        self.object_id = object_id
        if obs.artist:
            self.artist = obs.artist
        if obs.version:
            self.version = obs.version
        if self.scene == "music" and obs.visible_text:
            self.lyric = obs.visible_text[0][:80]
        if point:
            self.progress = point[:180]
            self.topic_id = f"{self.object_id}:{_slug(point)}"
        elif object_id != object_before:
            self.topic_id = f"{object_id}:none"
        self.phase = self._phase(obs)
        self.facts = self._facts(obs)
        self.inferences = self._inferences()
        self.unknowns = self._unknowns(obs)
        if self.scene != scene_before:
            self._replan("场景")
        elif object_id != object_before:
            self._replan("对象")
        elif self.phase != phase_before:
            self._replan("阶段")
        elif not self.plan:
            self._replan("开始")
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
            channel=obs.channel,
        )

    def blocks(self) -> str:
        facts = "；".join(self.facts) or "这一眼没有确认的屏幕事实"
        inferred = "；".join(self.inferences) or "没有额外推断"
        unknown = "；".join(self.unknowns) or "没有明确的未知项"
        plan = self.plan or {}
        attention = "、".join(str(item) for item in (plan.get("attention") or []))
        silence = "、".join(str(item) for item in (plan.get("silence_when") or []))
        talking = f"他刚说：{self.user_line}。先接这个，不要追着新画面。" if self._holding() and self.user_line else ""
        music = ""
        if self.scene == "music":
            music = (
                f"歌名：{self.title or '没确认'}。歌手：{self.artist or '没确认'}。"
                f"版本：{self.version or '没确认'}。歌词：{self.lyric or '没确认'}。"
                f"换歌：{'是' if self.song_changed else '否'}。他谈过：{'是' if self.user_mentioned else '否'}。"
            )
        state = {
            "fresh": "画面还新鲜。",
            "stalled": "画面停滞。不知道他是否还在看。",
            "invalid": "来源失效。不要根据这之前的画面主动开口。",
        }.get(self.watch_state, "")
        back = ("背景：" + "；".join(self.background) + "。") if self.background else ""
        origin = {
            "audio": "这一眼的原文是听到的，不是从画面上认的字。",
            "window": "这一眼的文字来自前台窗口，不是从画面上认的字。",
        }.get(self.channel, "")
        return "\n".join([
            "【来源】当前信息来自屏幕。屏幕上的人物和情节不是用户。" + origin,
            f"【理解】场景：{self.scene}。对象：{self.title or '还没确认'}。进展：{self.progress or '没有新进展'}。话题：{self.topic_id or '无'}。",
            music,
            state,
            back,
            f"事实：{facts}。",
            f"推断：{inferred}。",
            f"未知：{unknown}。",
            talking,
            self._steer_line(),
            f"【陪伴】{plan.get('mode') or '在旁边'}。{plan.get('goal') or '在旁边看着'}。留意：{attention or '确认得到的名字和原文'}。不说的时候：{silence or '没有值得交给她的点'}。",
            "导演没有替你形成看法。你可以有感受，也可以不说。",
        ]).strip()

    def _steer_line(self) -> str:
        parts = []
        if self.attention:
            parts.append(f"他让你留意画面里的：{self.attention}。")
        if self.talk == "more":
            parts.append("他想多听一点，仍然只说画面里的事。")
        elif self.talk == "quiet":
            parts.append("他让你先别说。")
        return "".join(parts)

    def _on_attention(self, obs: Observation) -> bool:
        want = (self.attention or "").strip()
        if not want:
            return True
        if want in {"字幕", "台词", "原文"} and _speakable(obs):
            return True
        if want in {"报错", "错误"} and self.phase == "stuck":
            return True
        blob = " ".join(
            [obs.change or "", self._summary(obs), *obs.visible_text, *obs.visible_events]
        )
        if want in blob:
            return True
        noun = re.sub(r"^(这|那)?(一只|一个|个|只)?", "", want)
        if noun and noun in blob:
            return True
        if len(noun) >= 2 and any(noun[i:i + 2] in blob for i in range(len(noun) - 1)):
            return True
        return False

    def _holding(self) -> bool:
        return time.time() < self.hold_until and bool(self.focus_object_id)

    def _advance_scene(self, scene: str, *, explicit: bool = False) -> None:
        if scene == "unknown" or scene == self.scene:
            self.pending_scene = ""
            self.pending_hits = 0
            return
        if scene == self.pending_scene:
            self.pending_hits += 1
        else:
            self.pending_scene = scene
            self.pending_hits = 1
        if not explicit and self.pending_hits < 2 and self.scene != "unknown":
            return
        self.scene_generation += 1
        self.scene = scene
        self.scene_id = f"{self.scene_generation}:{scene}"
        self.pending_hits = 0
        self.pending_scene = ""
        self.revision += 1

    def _phase(self, obs: Observation) -> str:
        blob = " ".join([obs.stage, obs.change, obs.title, *obs.visible_text, *obs.visible_events]).lower()
        if self.scene == "code":
            if any(word in blob for word in ("看不懂", "看不清这段", "无法确认")):
                return "unread"
            if any(word.lower() in blob for word in _ERROR):
                return "stuck"
            if any(word.lower() in blob for word in _PASSED):
                return "passed"
            return "flowing"
        if self.scene == "slides":
            if any(word in blob for word in ("放映", "演示", "slideshow")):
                return "showing"
            if any(word in blob for word in ("校对", "检查")):
                return "proof"
            if any(word in blob for word in ("排版", "字体", "对齐")):
                return "layout"
            if any(word in blob for word in ("结构", "大纲")):
                return "structure"
            return "editing"
        return ""

    def _facts(self, obs: Observation) -> list[str]:
        lines: list[str] = []
        if obs.app and _real_title(obs.app):
            lines.append(f"界面是{obs.app}")
        if obs.window and _real_title(obs.window):
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

    def _replan(self, reason: str) -> None:
        self.plan = self._build_plan()
        self.plan_revision += 1
        self.plan_reason = reason

    def _build_plan(self) -> dict[str, object]:
        common_silence = ["只有画面在动", "和刚说过的是同一个点", "他正在说别的"]
        replan = ["用户开口提出新的陪伴需求", "场景或对象改变", "阶段变了", "原来的理解被证伪"]
        table: dict[str, dict[str, object]] = {
            "music": {
                "mode": "一起听歌",
                "goal": "把能确认的歌名、歌手、歌词交给她，不预设她有共鸣",
                "attention": ["歌名", "歌手", "版本", "具体歌词", "是否换歌", "他有没有主动谈过"],
                "allowed": ["用确认到的歌名、歌手、歌词形成她自己的反应"],
                "silence_when": common_silence + ["没有确认到歌或歌词", "用伤感歌词推断他的心情"],
                "replan_when": replan,
            },
            "movie": {
                "mode": "一起看电影",
                "goal": "片名稳定，情节跟着可见画面更新，不剧透",
                "attention": ["当前可见情节", "他主动提起的人和疑问"],
                "allowed": ["对刚刚看见的具体情节有自己的短反应"],
                "silence_when": common_silence + ["可能剧透", "还不知道后面的情节"],
                "replan_when": replan,
            },
            "video": {
                "mode": "陪着刷",
                "goal": "一条一条看，可以跳过，他没聊完的上一条先留着",
                "attention": ["这条的标题", "具体在讲的那一点"],
                "allowed": ["一条里真有具体内容时交给她"],
                "silence_when": common_silence + ["只是换了一条，没有具体内容"],
                "replan_when": replan,
            },
            "code": {
                "mode": "坐在旁边",
                "goal": "顺手写就别打扰；卡住才把那个坎交给她；他来问就讨论",
                "attention": ["文件名", "报错原文", "是在写、在查，还是跑过了"],
                "allowed": ["把还在的报错原文交给她", "他来问时进入讨论"],
                "silence_when": common_silence + ["正在顺利编写", "看不懂却假装看懂"],
                "replan_when": replan,
            },
            "slides": {
                "mode": "看着这份稿",
                "goal": "看这一页想表达什么，不盯着每一次改字",
                "attention": ["这一页的标题和观点", "是在搭结构、改页、排版、校对还是放映"],
                "allowed": ["新的一页有明确观点时交给她"],
                "silence_when": common_silence + ["还在同一页调字体、对齐或措辞"],
                "replan_when": replan,
            },
            "game": {
                "mode": "坐在旁边",
                "goal": "先看懂这一局的可见局面，不代操作",
                "attention": ["局内可见的变化"],
                "allowed": ["局面出现明确变化时交给她"],
                "silence_when": common_silence + ["只是画面在动"],
                "replan_when": replan,
            },
        }
        plan = dict(table.get(self.scene) or {
            "mode": "在旁边",
            "goal": "先看着，不确定就不交点",
            "attention": ["确认得到的名字"],
            "allowed": [],
            "silence_when": common_silence,
            "replan_when": replan,
        })
        if self.phase == "stuck":
            plan["goal"] = "他把同一个坎留在屏幕上。把报错原文交给她，不替她鼓励"
        elif self.phase == "passed":
            plan["goal"] = "刚才那个坎过去了。她可以轻轻确认，然后安静"
        elif self.phase == "flowing":
            plan["goal"] = "他在顺手写。这一眼不交点"
        elif self.phase == "unread":
            plan["goal"] = "这段代码看不懂。承认看不懂，不假装掌握"
        elif self.phase == "layout":
            plan["goal"] = "还在同一页上排。通常安静"
        elif self.phase == "showing":
            plan["goal"] = "正在放映。看这一页在表达什么"
        return plan

    def _worth(self, obs: Observation) -> bool:
        if obs.quiet or self.scene == "unknown":
            return False
        if _same_point(self.topic_id, self.last_offered_topic):
            return False
        if self.scene == "code" and self.phase == "flowing":
            return False
        if self.scene == "code" and self.phase == "unread" and self.unread_noted:
            return False
        if self.scene == "slides" and self.phase == "layout":
            return False
        if self.scene == "code" and self.phase == "passed" and self.passed_noted:
            return False
        if self.scene == "video" and not _speakable(obs):
            return False
        if self.talk == "quiet":
            return False
        if self.attention and not self._on_attention(obs):
            return False
        if self.misses >= 3 and not _speakable(obs) and self.phase != "stuck":
            return False
        if not (obs.title or obs.visible_text or _specific(obs.visible_events) or self.phase in {"stuck", "passed"}):
            return False
        if not self._summary(obs):
            return False
        if self.phase == "passed":
            self.passed_noted = True
        if self.phase == "unread":
            self.unread_noted = True
        return True

    def _summary(self, obs: Observation) -> str:
        bit = _speakable(obs)
        if not bit:
            return ""
        name = self.title or ""
        if not name or name == bit or not _line(name):
            return bit[:180]
        return f"{name}：{bit}"[:180]


def _same_point(left: str, right: str) -> bool:
    """「作者」和「作者：蹄宝王」是同一个点，不连着交三次。"""
    a = (left or "").split(":")[-1]
    b = (right or "").split(":")[-1]
    if not a or not b or a == "none" or b == "none":
        return False
    return a == b or a in b or b in a


def _slug(text: str) -> str:
    kept = re.sub(r"\s+", "", text or "")
    return kept[:40] or "none"


situation = Situation()
