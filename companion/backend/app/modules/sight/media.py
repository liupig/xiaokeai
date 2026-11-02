"""Media identity, current content and provenance. Platform != film/song title."""
from __future__ import annotations

import re
import time

KINDS = {"movie", "video", "music"}
EXPERIENCE = {
    "movie": "接当前动作、台词和声音的情绪，短说一句，把对白时间留给片子。只按已确认的称呼说人物，不靠脸猜演员。不知道片名也能接眼前；只见一帧不推断完整剧情。",
    "series": "这是电视剧：保留已确认的剧名和集数，只讨论当前这一集已经看到的内容。换集、片头和回顾不算新剧情，不串接上一集的台词，不提前解释悬念。",
    "video": "每条视频是独立内容。接眼前的动作、笑点或明确观点，不把创作者当用户，不把推荐、评论、封面当正在播放。快速划走时先等内容稳定，不追着上一条说。",
    "music": "保留歌名、歌手和版本的来源，接已听清的歌词或已观察到的演出。没有音频证据不声称听到了节奏、音色和乐器；不续唱未知歌词，不把歌词经历套在用户身上。",
}


def company(kind: str, facts: dict[str, str]) -> str:
    key = "series" if kind == "movie" and facts.get("内容类型") == "电视剧" else kind
    return EXPERIENCE.get(key, "")
EMPTY = {"", "空", "无", "没有", "未知", "没变", "没看清", "看不清"}
PLATFORMS = {"网易云音乐", "网易云", "qq音乐", "酷狗音乐", "酷我音乐", "spotify", "apple music", "netflix", "ネットフリックス", "넷플릭스", "유튜브", "ユーチューブ", "ニコニコ動画", "tiktok", "ティックトック", "틱톡", "melon", "멜론",
             "youtube", "youtube music", "抖音", "抖音-记录美好生活", "记录美好生活", "哔哩哔哩", "b站",
             "爱奇艺", "腾讯视频", "优酷", "netflix", "potplayer", "vlc", "本地播放器", "播放器"}
LABELS = {"名字": "标题", "片名": "标题", "剧名": "标题", "歌名": "标题", "title": "标题", "artist": "歌手",
          "歌词": "这一句", "字幕": "这一句", "line": "这一句", "这一条": "这一句", "caption": "这一句"}


def title(raw: str, platform: str = "") -> str:
    value = (raw or "").strip()
    if not value or value.lower() in PLATFORMS or value == platform:
        return ""
    for suffix in (" - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox", " - PotPlayer", " - VLC media player"):
        value = value.removesuffix(suffix)
    if " - " in value:
        left, right = value.rsplit(" - ", 1)
        if right.lower() in PLATFORMS or right == platform:
            value = left.strip()
    value = re.sub(r"\.(?:mkv|mp4|avi|mov|mp3|flac|wav|m4a)$", "", value, flags=re.I)
    return "" if value.lower() in PLATFORMS or re.match(r"https?://", value) else value[:160]


def clean(raw: str) -> str:
    value = (raw or "").strip()
    if value in EMPTY or re.search(r"看不清|认不准|有把握才写|没有就空着|陪看电影电视剧|陪看视频|陪看音乐|只能写一个", value):
        return ""
    return value[:180]


def normalize(text: str, slots: dict[str, str]) -> dict[str, str]:
    from .media_language import field
    slots = {field(k): v for k, v in slots.items()}
    frames = [(int(match.group(1)), value) for key, value in slots.items()
              if (match := re.fullmatch(r"第(\d+)张", key))]
    if frames:
        usable = [(n, clean(v)) for n, v in frames if clean(v) and not re.search(r"聊天窗口|动漫角色|陪看记录", v)]
        if usable:
            slots["画面"] = sorted(usable)[-1][1]
    elif not slots and clean(text) and len(text.strip()) >= 4:
        slots["画面"] = clean(text)
    return slots


def inputs(desk, text: str, heard: str, *, metadata: dict | None = None, echo: bool = False) -> str:
    """Merge independent signals without turning audio into a visible subtitle."""
    metadata = metadata or {}
    lines = [text] if text.strip() else []
    explicit_title = any(re.match(r"^(标题|歌名|片名|剧名)[:：]\s*\S", row) for row in text.splitlines())
    actual = title(str(metadata.get("title") or desk.title), desk.app)
    if re.search(r"播放状态[:：]\s*unavailable", text) and not metadata.get("title"):
        actual = ""
    if actual and (metadata.get("title") or not explicit_title):
        lines += ["标题：" + actual, "标题来源：" + ("媒体会话" if metadata.get("title") else "窗口")]
    for key, label in (("artist", "歌手"), ("status", "播放状态"), ("position", "播放位置")):
        if key == "status" and re.search(r"播放状态[:：]\s*(?:unavailable|paused)", text):
            continue
        if key in metadata and str(metadata[key]).strip():
            lines.append(f"{label}：{metadata[key]}")
    if heard and not echo:
        lines.append("听到：" + heard)
    return "\n".join(lines)


def update(sub, current: str, previous: dict[str, str], incoming: dict[str, str]) -> tuple[str, dict[str, str]]:
    from .media_language import field, status as playback_status, episode as episode_number
    slots = {LABELS.get(field(k), field(k)): clean(v) for k, v in incoming.items()}
    if slots.get("播放状态"):
        slots["播放状态"] = playback_status(slots["播放状态"])
    name = title(slots.get("标题", ""), sub.label)
    old_name = previous.get("标题", "")
    changed = bool(name and name != old_name)
    changed = changed or bool(re.search(r"换了一条|切换视频|下一条|换歌|新的一条", slots.get("变化", "")))
    episode = slots.get("集数", "")
    if not episode and name:
        match = episode_number(name)
        if match:
            episode = slots["集数"] = match
            slots["内容类型"] = "电视剧"
    changed = changed or bool(episode and previous.get("集数") and episode != previous["集数"])
    version = slots.get("版本", "")
    changed = changed or bool(version and previous.get("版本") and version != previous["版本"])
    stable = {k: v for k, v in previous.items() if k in {"标题", "歌手", "版本", "集数", "内容类型", "播放位置", "播放状态", "观测时刻"}}
    if stable.get("播放状态") == "unavailable":
        stable.pop("播放状态", None)
    if changed:
        stable = {}
    facts = dict(stable)
    for key in ("标题", "歌手", "版本", "集数", "内容类型", "播放位置", "播放状态", "画面", "原文", "这一句", "听到", "标题来源"):
        if key == "标题":
            continue
        if slots.get(key):
            facts[key] = slots[key]
    if name:
        facts["标题"] = name
    status = facts.get("播放状态", "").lower()
    if slots.get("阶段") == "paused":
        status = facts["播放状态"] = "paused"
    elif slots.get("阶段") == "playing":
        status = facts["播放状态"] = "playing"
    blob = slots.get("画面", "") + slots.get("原文", "")
    if re.search(r"正在播放广告|片头广告|广告倒计时|缓冲|加载中|会员试看", slots.get("画面", "")):
        facts["播放状态"] = "unavailable"
    phase = "paused" if status in {"paused", "暂停", "已暂停"} else current
    if status in {"playing", "播放", "正在播放"} or any(slots.get(k) for k in ("画面", "原文", "这一句", "听到")):
        phase = "playing" if sub.phase("playing") else current
    if status in {"paused", "暂停", "已暂停"}:
        phase = "paused" if sub.phase("paused") else current
    if sub.kind == "movie" and re.search(r"演职员表|片尾字幕|片尾曲|THE END", blob, re.I):
        phase = "credits"
    if changed:
        facts["内容切换"] = "是"
        facts.pop("听到", None)  # audio acquired before the visual switch belongs to the old item
    try:
        if "播放位置" in slots and "播放位置" in previous:
            elapsed = max(0, time.monotonic()-float(previous.get("观测时刻", time.monotonic())))
            delta = float(slots["播放位置"])-float(previous["播放位置"])
            expected = elapsed if previous.get("播放状态") == "playing" else 0
            if delta < -1 or abs(delta-expected) > 8:
                facts["跳转"] = "是"
                facts.pop("听到", None)
        if "播放位置" in slots:
            facts["观测时刻"] = str(time.monotonic())
    except ValueError:
        pass
    return phase, facts


def handoff(sub, phase, facts: dict[str, str]) -> str:
    name = title(facts.get("标题", ""), sub.label)
    if name and facts.get("集数") and facts["集数"] not in name:
        name += " " + facts["集数"]
    if name and facts.get("版本"):
        name += "（" + facts["版本"] + "）"
    lines = [f"界面：{sub.label}", f"类型：{sub.scene}"]
    if name:
        lines.append("标题：" + name)
    if facts.get("歌手"):
        lines.append("歌手：" + facts["歌手"])
    blocked = facts.get("播放状态") in {"paused", "暂停", "已暂停", "unavailable", "stopped"}
    if not blocked:
        visible = facts.get("这一句") or facts.get("原文")
        if visible and visible not in {name, facts.get("歌手")}:
            lines.append("原文：" + visible)
        if facts.get("画面"):
            lines.append("画面：" + facts["画面"])
        if facts.get("听到") and not visible:
            lines.append("原文：" + facts["听到"])
    lines.append("变化：" + ("内容切换，中间不保证连续" if facts.get("内容切换") or facts.get("跳转") else phase.label))
    return "\n".join(lines)


def prompt(kind: str) -> str:
    label = {"movie": "电影电视剧", "music": "音乐", "video": "视频"}[kind]
    return f"陪看{label}。只看最后一张，写当前的一句真实内容。用画面：描述动作，用原文：照抄字幕或歌词，保留中文、English、日本語、한국어原文和空格，不翻译。看不清留空。搜索页和登录页写播放状态：unavailable。不要抄推荐列表、评论和播放按钮，不猜人名和后续剧情。"
