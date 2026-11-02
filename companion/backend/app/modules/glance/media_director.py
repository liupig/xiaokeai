"""Quiet, current, spoiler-free reactions for films, series, feeds and music."""
import re


def bind_context(offer, sight: dict) -> None:
    """Freeze verified identity after attention filtering has selected a point."""
    slots = sight.get("slots") or {}
    context = []
    for key, label in (("title", "标题"), ("episode", "集数"), ("artist", "歌手"), ("version", "版本")):
        value = slots.get(key)
        if value and value not in offer.summary and not any(value in row for row in context):
            context.append(label + "：" + value)
    context.append(offer.summary)
    for row in str(sight.get("handoff") or "").splitlines():
        if row.startswith("画面：") and row[3:] not in offer.summary:
            context.append(row)
    offer.summary = "\n".join(context)[:500]


def cadence(scene: str, *, elapsed: float, opening: bool, talk: str, playback: str) -> bool:
    if talk == "quiet" or playback in {"paused", "暂停", "已暂停", "stopped", "unavailable"}:
        return False
    gap = {"movie": 35, "music": 30, "video": 18}.get(scene, 30)
    if talk == "more":
        gap /= 2
    return opening or elapsed >= gap


def unsupported_reply(evidence: str, spoken: str) -> str:
    if re.search(r"\b(?:the killer is|in the next episode|the ending is|he will die|she will die|the next lyric is)\b|次回.{0,12}(?:死|犯人)|犯人は|結末は|次の歌詞は|다음\s*(?:회|화).{0,16}(?:죽|범인)|범인은|결말은|다음\s*가사는", spoken, re.I):
        return "不要提前透露未看到的情节或续写歌词"
    if re.search(r"you (?:must|definitely).{0,20}(?:heartbroken|miss your ex)|あなたは.{0,12}(?:失恋|元彼)|너는.{0,12}(?:실연|전남친)", spoken, re.I):
        return "字幕、歌词和人物的经历不等于用户经历"
    for sound in ("raindrops", "rain sounds", "drumbeat", "vocal tone", "guitar sound", "piano sound", "first verse", "chorus", "雨音", "歌声", "声色", "サビ", "ビート", "빗소리", "목소리", "음색", "후렴", "첫 소절"):
        if sound.casefold() in spoken.casefold() and sound.casefold() not in evidence.casefold():
            return "没有当前证据，不要编造声音细节或歌曲结构"
    for sound in ("雨声", "鼓点", "音色", "吉他声", "钢琴声", "低音", "高音", "转音", "唱得", "唱腔", "嗓音", "声线", "编曲"):
        if sound in spoken and sound not in evidence:
            return "没有声音细节证据，不要把字幕或歌词想象成实际听到的声音"
    for order in ("第一句", "第二句", "副歌", "前奏", "间奏"):
        if order in spoken and order not in evidence:
            return "未确认歌曲结构和位置，不要把当前歌词当成第一句或副歌"
    if re.search(r"下一句(?:是|就|唱)|接下来的歌词|后面一句", spoken):
        return "不要续写没听到或没看到的歌词"
    if re.search(r"你(?:一定|肯定|就是).*(?:失恋|难过|想前任|哭了)|你失恋|你在想前任", spoken):
        return "字幕、歌词和人物的经历不等于用户经历"
    if re.search(r"凶手(?:其实)?是|结局(?:是|会)|后面(?:他|她|会)|下一集(?:会|他|她)|最后(?:他|她).*(?:死|离开)|原来他是", spoken):
        return "不要提前透露未看到的情节"
    quotes = re.findall(r"[「『“\"]([^」』”\"]{4,})[」』”\"]", spoken)
    if any(quote not in evidence for quote in quotes):
        return "不要补写未确认的台词或歌词"
    performers = re.findall(r"(?:是|由)([\u4e00-\u9fffA-Za-z·]{2,12}?)(?:唱的|演唱|饰演|主演|演的)", spoken)
    if any(name not in evidence for name in performers):
        return "歌手、演员需要当前可验证的来源"
    return ""
