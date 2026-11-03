"""Conservative OCR extraction; comments and playlists are not subtitles."""
import re
from urllib.parse import urlsplit, parse_qs

CONTROL = re.compile(r"评论|点赞|关注|分享|收藏|下载|推荐|会员|登录|倍速|清晰度|弹幕|设置|播放列表|下一首|上一首|搜索|https?://|\b(?:comments?|subscribe|sign in|log in|playlist|search|recommended|download|settings)\b|コメント|おすすめ|ログイン|検索|再生リスト|댓글|추천|로그인|검색|재생목록", re.I)


def identity(lines: list[dict], height: int) -> str:
    """Read a video URL only from browser chrome, never from a comment/link."""
    for row in lines:
        words = row.get("words") or []
        if not words or max(float(w.get("y", 0)) for w in words) > height * .15:
            continue
        match = re.search(r"(?:https?://)?(?:www\.)?(?:douyin\.com|bilibili\.com|youtube\.com|youtu\.be)/[^\s]+", str(row.get("text") or ""), re.I)
        if not match:
            continue
        raw = match.group(0)
        parsed = urlsplit(raw if "://" in raw else "https://" + raw)
        query = parse_qs(parsed.query)
        for key in ("modal_id", "aweme_id", "v", "bvid"):
            value = query.get(key, [""])[0]
            if re.fullmatch(r"[\w-]{6,32}", value):
                return f"{parsed.hostname}:{value}"
        if re.fullmatch(r"/(?:video/)?[A-Za-z0-9_-]{6,32}/?", parsed.path) and parsed.path not in {"/jingxuan", "/search"}:
            return f"{parsed.hostname}:{parsed.path.strip('/')}"
    return ""


def page_state(lines: list[dict]) -> str:
    text = "\n".join(re.sub(r"\s+", "", str(row.get("text") or "")).lower() for row in lines)
    if re.search(r"bing\.com/search|google\.[^/\n]+/search|百度一下|相关搜索|搜索结果|约[\d,，]+个结果|searchresults|relatedsearches|検索結果|関連検索|검색결과|관련검색", text):
        return "搜索结果页，尚未确认正在播放"
    if re.search(r"扫码登录|登录后观看|请先登录|登录后播放|signintowatch|logintowatch|ログインして視聴|ログインが必要|로그인후시청|로그인이필요", text):
        return "登录页，尚未确认正在播放"
    return ""


def combine(text: str, lines: list[dict], image_size: tuple[int, int], kind: str) -> str:
    state = page_state(lines)
    if state:
        return "画面：" + state + "\n播放状态：unavailable"
    # Small local models sometimes copy their instruction as an imagined subtitle.
    text = "\n".join(row for row in text.splitlines() if not re.search(r"陪看电影电视剧|陪看视频|陪看音乐|只看最后一张|用画面[:：]|照抄字幕|搜索页和登录页|看不清留空|不要抄推荐|不猜人名", row))
    return "\n".join(part for part in (text, facts(lines, image_size, kind)) if part)


def facts(lines: list[dict], image_size: tuple[int, int], kind: str) -> str:
    result = []
    captions = []
    width, height = image_size
    media_id = identity(lines, height)
    if media_id:
        result.append("媒体标识：" + media_id)
    if page_state(lines):
        return "画面：" + page_state(lines) + "\n播放状态：unavailable"
    for row in lines:
        text = " ".join(str(row.get("text") or "").split())
        compact = re.sub(r"\s+", "", text).lower()
        if compact in {"广告", "加载中", "正在缓冲", "已暂停", "paused", "buffering", "loading", "一時停止", "読み込み中", "일시정지", "일시중지", "버퍼링", "로딩중"}:
            result.append("播放状态：" + ("paused" if compact in {"已暂停", "paused", "一時停止", "일시정지", "일시중지"} else "unavailable"))
        explicit = re.match(r"^([^:：]{1,24})[:：]\s*(.{1,100})$", text)
        if explicit:
            # Imported normally in backend, dynamically by the isolated eye worker.
            labels = {"歌名": "标题", "片名": "标题", "剧名": "标题", "歌手": "歌手", "集数": "集数", "版本": "版本", "字幕": "字幕", "歌词": "歌词",
                      "title": "标题", "artist": "歌手", "subtitle": "字幕", "subtitles": "字幕", "lyrics": "歌词", "episode": "集数",
                      "タイトル": "标题", "曲名": "标题", "作品名": "标题", "歌詞": "歌词", "アーティスト": "歌手", "話数": "集数",
                      "제목": "标题", "곡명": "标题", "가수": "歌手", "아티스트": "歌手", "자막": "字幕", "가사": "歌词", "회차": "集数"}
            label = labels.get(explicit.group(1).strip().lower())
            if label:
                result.append(label + "：" + explicit.group(2))
                continue
        if CONTROL.search(text) or re.fullmatch(r"[\d\W]+", text):
            continue
        words = row.get("words") or []
        # Browser chrome is expected around web video. Filter each UI row and
        # use subtitle geometry, rather than suppressing every subtitle as soon
        # as a Search/Login button is present anywhere on the screen.
        if not words or kind == "music":
            continue
        left = min(float(w.get("x", 0)) for w in words)
        right = max(float(w.get("x", 0))+float(w.get("width", 0)) for w in words)
        y = max(float(w.get("y", 0)) for w in words)
        if width*.2 < (left+right)/2 < width*.8 and height*.62 < y < height*.9 and 4 <= len(text) <= 70:
            captions.append((y, text))
    for _, text in sorted(captions)[-2:]:
        result.append("字幕：" + text)
    return "\n".join(result)
