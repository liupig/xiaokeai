"""MiniCPM-V 4.7 1B：连续截屏，模型看当前画面。"""
from __future__ import annotations

import base64
import io
import os
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any, Dict, Optional

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ROOT = Path(__file__).resolve().parent
MODEL_DIR = Path(os.environ.get("MINICPM_V47_MODEL") or (ROOT.parent / "models" / "MiniCPM-V-4.7-1B"))

DEFAULT_PROMPT = (
    "用两三句记这一眼，写成能接着读的叙事。不要列表。"
    "先写他正在用的软件和文件名或标题，再写画面上能读到的一行字，最后说他在做的动作。"
    "画面中间若站着动漫角色，那是旁边的人，不要写她。"
    "看不清的名字不要编。抓不住重点就只写没变。"
)
SHARP_PROMPT = (
    "上一句没抓住重点。用两三句写出软件或文件的名字，以及画面上的一句原文。没有就只写没变。"
)
WATCH_PROMPT = (
    "你在连续观察屏幕。只用一句中文，最多40字，说这段录屏里最值得注意的事实。"
    "首次或内容切换时交代主要内容；之后只说新发生的事件、关键动作或状态变化。"
    "游戏关注交战和阶段变化，视频关注人物行为和情节，软件关注页面和任务状态。"
    "字幕只在解释关键事件且确实看清时引用，不逐句抄写，不编名字。"
    "只看主要应用或视频，忽略识别工具的面板、预览、历史记录和黑色遮罩。"
    "同一场景的凝视、眨眼、轻微移动或装饰特效不必报告。"
    "不把场景当标题，不写标题、原文、新动作等栏目，不推测意图。"
    "只输出一条事实，不重复叙述；没有实质新变化就只写没变。"
)
SCENE_PROMPTS = {
    "auto": (
        "自动判断主要场景。首次说明内容；之后只报告明确的新事件、界面切换或状态变化。"
    ),
    "video": (
        "这是短视频/信息流陪看。每条视频都是独立内容：先等新视频画面稳定，再交代当前这条在演什么；"
        "之后只报告明确的镜头切换、人物关系、笑点或观点推进。"
        "推荐流、评论、封面、点赞和创作者主页不算正在播放；不要把创作者或视频人物当用户。"
        "快速划走时不延续上一条的剧情，不逐句抄字幕，也不把微表情、凝视和背景特效当事件。"
    ),
    "movie": (
        "这是电影或剧集陪看。只接当前已经看到的人物、地点、冲突和情节转折；关键台词确实决定情节时才简短引用。"
        "不知道片名也只说眼前，不凭脸猜演员；换集、片头、回顾、片尾和字幕换行不算新剧情。"
        "绝不预告后续、解释悬念或串接未看到的剧情。"
    ),
    "music": (
        "这是音乐陪看。先识别播放器是否播放、暂停、加载、报错或受限；有明确错误码、登录限制或无法播放时优先报告该状态，"
        "不要把错误页当作歌曲内容。只在画面或播放器明确显示时说歌名、歌手、版本和播放/暂停/换歌；演出画面变化可以简短说。"
        "没有音频证据，不要声称听到了节奏、音色、乐器、前奏或副歌；不要续写歌词，也不把歌词经历套在用户身上。"
        "不逐句抄歌词，除非用户明确要求。"
    ),
    "game": (
        "这是游戏陪玩。首次交代游戏和可确认的阶段；之后优先报告选人、加载完成、进入对局、开战、明确击杀/死亡、目标争夺、回城、结算和胜负。"
        "游戏直播分类页、推荐卡片、赛事海报、封面缩略图、主播列表或回放列表都不等于正在对局；这类画面必须只输出“正在浏览游戏直播列表”，"
        "不能提玩家、角色、敌人、选人、开战、目标争夺或剧情推进。"
        "镜头中心、队友、敌人或选中单位不等于玩家本人；看不清英雄、分路、装备、战绩和胜负就不说。"
        "没有明确结果，不报击杀、龙、连杀或战术指令；不报告待机、镜头轻移、普通小兵移动或无结果技能特效。"
    ),
    "work": (
        "这是工作/普通屏幕陪伴。首次只说正在使用的应用、文件或任务；之后只报告页面切换、运行开始/结束、明确报错或文档/幻灯片进入展示等任务状态。"
        "文件名、报错和结果必须看清才说；没看到输出，不要说代码通过或失败；不要逐字复述文档，也不替用户操作或下结论。"
    ),
}
SCENE_LABELS = {
    "auto": "自动", "video": "刷视频", "movie": "看电影/剧集",
    "music": "听音乐", "game": "陪玩游戏", "work": "工作/普通屏幕",
}
# A new inference should normally see a new slice of time, rather than almost
# the same rolling window. Game remains more responsive for concrete events.
SCENE_CADENCE_SECONDS = {
    "auto": 4.0,
    "video": 5.0,
    "movie": 10.0,
    "music": 10.0,
    "game": 3.0,
    "work": 5.0,
}
WATCH_SHARP = SHARP_PROMPT
OBSERVE_PROMPT = (
    "这几张是电脑屏幕，从早到晚。只写屏幕上新出现的事实。"
    "不要写心情，不要把画面里的人写成用户，不要写中间的动漫角色。看不清不要编。\n"
    "没有新的标题、原文或情节，只写没变。无新变化、Unknown、No new 都算没变，不要写出来。\n"
    "中间那个人即使很大也不要写，去看她旁边的视频、字幕和标题。"
    "YouTube、B站、抖音写 video，不要写 movie。\n"
    "有新事实才写，一行一项，必须用中文冒号，不要写说明，没有内容的行不要写。"
    "原文只抄字幕或标题上的那一句，不要写视频播放、评论区、点赞数，不要写左边右边的人。"
    "变化不要写一共几张。类型只写 movie、music、video、code、slides、other、unknown 里的一个词。\n"
    "界面：\n窗口：\n类型：\n标题：\n画面：\n原文：\n变化："
)
OBSERVE_SHARP = (
    "上一句把画面里的人写成了用户，或没写屏幕事实。"
    "只重写界面、窗口、类型、标题、画面、原文、变化。没有新事实就只写没变。"
)
FILM_PROMPT = (
    "用一句中文写这张图里正在发生的事。"
    "有字幕或标题就原样抄那一句。看不清不要编。边上的动漫角色不要写。"
    "没有人和字就只写没变。"
)
WINDOW_PROMPT = (
    "这几张是前台窗口里的原图，从早到晚。只写这块画面上新出现的事实。"
    "不要写心情，不要把画面里的人写成用户。看不清不要编。"
    "边上叠着的动漫角色是旁边的她，不要写她。\n"
    "没有新的标题、原文或情节，只写没变。无新变化、Unknown、No new 都算没变，不要写出来。\n"
    "YouTube、B站、抖音写 video，不要写 movie。\n"
    "有新事实才写，一行一项，必须用中文冒号，不要写说明，没有内容的行不要写。"
    "原文只抄字幕或标题上的那一句，不要写播放器按钮、评论区、点赞数。"
    "变化不要写一共几张。类型只写 movie、music、video、code、slides、other、unknown 里的一个词。\n"
    "界面：\n窗口：\n类型：\n标题：\n画面：\n原文：\n变化："
)

_lock = threading.Lock()
_infer_lock = threading.Lock()
_model = None
_processor = None
_image_mode = "image"
_watch: Optional[threading.Thread] = None
_stop = threading.Event()
_sub_lock = threading.Lock()
_subs: list[queue.Queue] = []
_state: Dict[str, Any] = {
    "ready": False,
    "loading": False,
    "running": False,
    "message": "未加载",
    "backend": "",
    "last_ms": 0,
    "last_text": "",
    "scene": "auto",
    "watch_revision": 0,
}


def _weights_ok() -> bool:
    if not (MODEL_DIR / "config.json").is_file():
        return False
    return any(MODEL_DIR.glob("*.safetensors")) or any(MODEL_DIR.glob("*.bin"))


def list_monitors() -> list[dict]:
    try:
        import mss
    except ImportError:
        return [{"index": 1, "label": "未安装 mss", "width": 0, "height": 0}]
    with mss.mss() as sct:
        out = []
        for i, mon in enumerate(sct.monitors):
            label = "全部拼在一起" if i == 0 else f"屏幕 {i}"
            out.append({
                "index": i,
                "label": f"{label} {mon['width']}x{mon['height']}",
                "width": mon["width"],
                "height": mon["height"],
            })
        return out


def status() -> Dict[str, Any]:
    st = dict(_state)
    st["weights_ok"] = _weights_ok()
    st["model_dir"] = str(MODEL_DIR)
    st["monitors"] = list_monitors()
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            st["cuda"] = f"{free / 1024 ** 3:.1f} / {total / 1024 ** 3:.1f} GB 空闲"
        else:
            st["cuda"] = "无 CUDA，会走 CPU"
    except Exception:
        st["cuda"] = "未装 torch"
    return st


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=32)
    with _sub_lock:
        _subs.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _sub_lock:
        if q in _subs:
            _subs.remove(q)


def publish(ev: dict) -> None:
    with _sub_lock:
        subs = list(_subs)
    for q in subs:
        try:
            q.put_nowait(ev)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(ev)
            except queue.Full:
                pass


def _set(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def load() -> Dict[str, Any]:
    global _model, _processor
    with _lock:
        if _model is not None:
            return status()
        if _state["loading"]:
            return status()
        _state["loading"] = True
        _state["message"] = "正在加载 MiniCPM-V 4.7 1B…"
    publish({"type": "status", **status()})
    try:
        if not _weights_ok():
            raise RuntimeError(f"还没有权重：{MODEL_DIR}。先在 v47 目录运行 .\\setup.ps1")
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            torch.backends.cudnn.benchmark = True
            torch.backends.cuda.enable_flash_sdp(True)
            torch.backends.cuda.enable_mem_efficient_sdp(True)
            torch.set_float32_matmul_precision("high")
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        attn = "sdpa"
        try:
            import flash_attn  # noqa: F401
            attn = "flash_attention_2"
        except Exception:
            attn = "sdpa"
        kwargs = {
            "local_files_only": True,
            "dtype": dtype,
            "attn_implementation": attn,
        }
        try:
            model = AutoModelForImageTextToText.from_pretrained(str(MODEL_DIR), **kwargs)
        except TypeError:
            kwargs.pop("dtype", None)
            kwargs["torch_dtype"] = dtype
            try:
                model = AutoModelForImageTextToText.from_pretrained(str(MODEL_DIR), **kwargs)
            except Exception:
                kwargs.pop("attn_implementation", None)
                attn = "sdpa"
                model = AutoModelForImageTextToText.from_pretrained(str(MODEL_DIR), **kwargs)
        except Exception:
            if attn != "sdpa":
                kwargs["attn_implementation"] = "sdpa"
                attn = "sdpa"
                model = AutoModelForImageTextToText.from_pretrained(str(MODEL_DIR), **kwargs)
            else:
                raise
        if torch.cuda.is_available():
            model = model.to("cuda")
        processor = AutoProcessor.from_pretrained(str(MODEL_DIR), local_files_only=True)
        model.eval()
        model.requires_grad_(False)
        name = "cuda" if torch.cuda.is_available() else "cpu"
        kind = "bf16" if dtype == torch.bfloat16 else "fp32"
        with _lock:
            _model = model
            _processor = processor
            _state["ready"] = True
            _state["loading"] = False
            _state["attn"] = attn
            _state["backend"] = f"MiniCPM-V-4.7-1B · {name} · {kind} · {attn}"
            _state["message"] = "模型已加载，正在预热"
    except Exception as exc:
        hint = str(exc)
        low = hint.lower()
        if "minicpmv4_7" in low or "does not recognize" in low or "unexpected" in low:
            hint += "。请用 v47\\.venv（transformers>=5.18），不要用上一级 o 4.5 的环境。"
        with _lock:
            _state["loading"] = False
            _state["ready"] = False
            _state["message"] = hint
        publish({"type": "error", "message": hint})
        raise
    publish({"type": "status", **status()})
    try:
        from PIL import Image
        blank = Image.new("RGB", (960, 540), (16, 16, 16))
        describe(
            blank,
            "只写没变",
            downsample="16x",
            max_slice_nums=1,
            max_new_tokens=8,
            frames=[blank, blank],
            do_sample=False,
            stream=False,
            preface=False,
        )
    except Exception:
        pass
    with _lock:
        _state["message"] = "模型已加载"
    publish({"type": "status", **status()})
    return status()


def _fit(img, max_edge: int, resample: int = 1):
    if max_edge <= 0:
        return img
    w, h = img.size
    long_edge = max(w, h)
    if long_edge <= max_edge:
        return img
    scale = max_edge / long_edge
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), resample)


# 半秒一张原图，留住两次理解之间的过程。一次送给模型的最多九张。
_REEL_EVERY = 0.5
_REEL_KEEP = 48
_REEL_MIN = 6
_REEL_SEND = 9
_REEL_OVERLAP = 1.5
_reel_lock = threading.Lock()
_reel_frames: list[tuple[float, object, bytes, int]] = []
_reel_seq = 0
_reel_consumed_seq = 0
_OVERLAP_FRAMES = 3
_reel_thread: Optional[threading.Thread] = None
_reel_token = 0
_reel_index = 1
_reel_mode = ""
_reel_consumed = 0.0
_reel_raw = (0, 0)


def frame_budget(count: int, detail: bool, busy: bool) -> int:
    """连续理解少送几张，仍然从早到晚均匀取，并保留窗口两头。细节确认只送最新一张。"""
    if detail or count <= 1:
        return 1
    if busy:
        return min(9, count)
    if count <= 3:
        return count
    return 5 if count >= 6 else 3


def _window_busy(sigs: list[bytes]) -> bool:
    if len(sigs) < 3:
        return False
    changed = 0
    for left, right in zip(sigs, sigs[1:]):
        if _outside_idle(left, right):
            changed += 1
    return changed >= max(2, len(sigs) // 3)


def _even(items: list, limit: int) -> list:
    if limit <= 0 or len(items) <= limit:
        return list(items)
    last = len(items) - 1
    picked: list[int] = []
    for i in range(limit):
        pos = round(i * last / (limit - 1))
        if picked and pos <= picked[-1]:
            pos = picked[-1] + 1
        if pos > last:
            break
        picked.append(pos)
    return [items[i] for i in picked]


def _advance_consumed(since: float, end: float) -> float:
    """下一窗从上一窗末尾往前重叠一小段，同一句歌词或同一处报错不会被切成两段。"""
    return max(since, end - _REEL_OVERLAP)


def _span_changed(sigs: list[bytes], follow: Optional[bytes]) -> bool:
    if follow is None:
        return True
    if any(_outside_idle(follow, sig) for sig in sigs):
        return True
    return any(_outside_idle(a, b) for a, b in zip(sigs, sigs[1:]))


def _reel_loop(index: int, token: int) -> None:
    global _reel_mode, _reel_seq, _reel_raw
    screen = _Screen(index)
    mode = screen.open()
    with _reel_lock:
        if token == _reel_token:
            _reel_mode = mode
    while True:
        with _reel_lock:
            if token != _reel_token:
                return
        raw = screen.grab()
        if raw is not None and getattr(raw, "size", None) and _bright_enough(raw):
            raw_w, raw_h = raw.size
            shot = _fit(raw, 1920)
            _reel_seq += 1
            item = (time.time(), shot, _sig(shot), _reel_seq)
            with _reel_lock:
                if token == _reel_token:
                    _reel_raw = (raw_w, raw_h)
                    _reel_frames.append(item)
                    del _reel_frames[:-_REEL_KEEP]
        time.sleep(_REEL_EVERY)


def _ensure_reel(index: int) -> None:
    global _reel_thread, _reel_token, _reel_index
    with _reel_lock:
        if _reel_thread is not None and _reel_thread.is_alive() and _reel_index == index:
            return
        _reel_token += 1
        token = _reel_token
        _reel_index = index
        _reel_frames.clear()
        _reel_thread = threading.Thread(
            target=_reel_loop, args=(index, token), daemon=True, name="glance-reel"
        )
        _reel_thread.start()


def _fresh_reel(after_seq: int) -> list:
    with _reel_lock:
        return [item for item in _reel_frames if item[3] > after_seq]


def _wait_reel(after_seq: int, want: int, timeout: float) -> list:
    deadline = time.time() + timeout
    got = _fresh_reel(after_seq)
    while len(got) < want and time.time() < deadline:
        time.sleep(0.1)
        got = _fresh_reel(after_seq)
    return got


def _dump_reel(images) -> None:
    try:
        folder = ROOT / "tmp"
        folder.mkdir(parents=True, exist_ok=True)
        images[-1].save(folder / "last-glance.jpg", quality=60)
        for old in folder.glob("reel-*.jpg"):
            old.unlink(missing_ok=True)
        for i, im in enumerate(images, 1):
            im.save(folder / f"reel-{i}.jpg", quality=55)
    except Exception:
        pass


def _jpeg_b64(img, max_edge: int, quality: int = 72) -> str:
    im = _fit(img, max_edge).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _show_frames(images, limit: int = 8):
    if len(images) <= limit:
        return list(images)
    if limit <= 1:
        return [images[-1]]
    step = (len(images) - 1) / (limit - 1)
    return [images[round(i * step)] for i in range(limit)]


def _lab_trace(captured, sent, prompt: str) -> dict:
    """调试页用的小图。不进对话。"""
    return {
        "captured": [_jpeg_b64(im, 1600, 85) for im in _show_frames(list(captured), 8)],
        "sent": [_jpeg_b64(im, 1920, 90) for im in list(sent)],
        "prompt": prompt or "",
    }


def _grab_mss(index: int):
    import mss
    from PIL import Image
    with mss.mss() as sct:
        mons = sct.monitors
        if index < 0 or index >= len(mons):
            index = 1 if len(mons) > 1 else 0
        raw = sct.grab(mons[index])
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


_camera = None


class _Screen:
    """优先 DXGI。mss 的 BitBlt 经常抓不到浏览器里正在播的视频。"""

    def __init__(self, index: int):
        self.index = index
        self.cam = None
        self.mode = "mss"

    def open(self) -> str:
        global _camera
        try:
            import bettercam
            if _camera is None:
                output_idx = 0 if self.index <= 1 else max(0, self.index - 1)
                _camera = bettercam.create(output_idx=output_idx, output_color="RGB")
            self.cam = _camera
            if not getattr(self.cam, "is_capturing", False):
                # Duplicate the latest desktop frame while idle as a recording
                # does; get_latest_frame otherwise blocks until screen damage.
                self.cam.start(target_fps=10, video_mode=True)
            self.mode = "dxgi"
        except Exception as exc:
            self.cam = None
            self.mode = f"mss ({exc})"
        return self.mode

    def grab(self):
        if self.cam is not None:
            from PIL import Image
            frame = self.cam.get_latest_frame()
            if frame is not None and getattr(frame, "size", 0):
                return Image.fromarray(frame)
        return _grab_mss(self.index)

    def close(self) -> None:
        if self.cam is None:
            return
        try:
            self.cam.stop()
        except Exception:
            pass
        self.cam = None


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.strip()


def _label_echo(text: str) -> bool:
    """模型把提示里的字段名抄回来时，当没看见。"""
    compact = re.sub(r"[\s：:，,。！!？?、]", "", text or "").lower()
    for word in (
        "界面", "窗口", "类型", "标题", "歌手", "版本", "阶段", "画面", "原文", "变化",
        "movie", "music", "video", "code", "slides", "other", "unknown", "没变",
        "pinkcartoon", "cartooncharacter", "humanoid", "nonew", "nonewfacts",
        "无新变化", "无新事实", "youtube",
    ):
        compact = compact.replace(word, "")
    for word in ("已记下的", "已经记下", "记下的屏幕事实"):
        compact = compact.replace(word, "")
    return len(compact) < 2


def _sig(img) -> bytes:
    return img.convert("L").resize((64, 36)).tobytes()


def _moved(a: bytes, b: bytes) -> bool:
    """整屏平均变化，或任意一小块变化。视频窗口只占屏幕一角时也能算变了。"""
    if not a or not b or len(a) != len(b):
        return True
    if _diff(a, b) >= 2.5:
        return True
    w, h, tile = 64, 36, 8
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            acc = n = 0
            for yy in range(y, min(y + tile, h)):
                row = yy * w
                for xx in range(x, min(x + tile, w)):
                    acc += abs(a[row + xx] - b[row + xx])
                    n += 1
            if n and acc / n >= 12:
                return True
    return False


def _same_frame(a: bytes, b: bytes) -> bool:
    return not _moved(a, b)


def _hot_tiles(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """64×36 上，哪几块的平均灰度变过了。"""
    if not a or not b or len(a) != len(b):
        return []
    w, h, tile = 64, 36, 8
    cols = (w + tile - 1) // tile
    rows = (h + tile - 1) // tile
    hot: list[tuple[int, int]] = []
    for ty in range(rows):
        for tx in range(cols):
            acc = n = 0
            for yy in range(ty * tile, min((ty + 1) * tile, h)):
                row = yy * w
                for xx in range(tx * tile, min((tx + 1) * tile, w)):
                    acc += abs(a[row + xx] - b[row + xx])
                    n += 1
            if n and acc / n >= 12:
                hot.append((tx, ty))
    return hot


def _blob_fraction(hot: list[tuple[int, int]]) -> float:
    if not hot:
        return 0.0
    xs = [p[0] for p in hot]
    ys = [p[1] for p in hot]
    cols, rows = 8, 5
    return ((max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)) / (cols * rows)


def _blob_count(hot: list[tuple[int, int]]) -> int:
    pending = set(hot)
    count = 0
    while pending:
        count += 1
        stack = [pending.pop()]
        while stack:
            x, y = stack.pop()
            for nxt in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nxt in pending:
                    pending.remove(nxt)
                    stack.append(nxt)
    return count


def _outside_idle(a: bytes, b: bytes) -> bool:
    """变化是不是超出了「一个角色在原地动」。

    一整块不到屏幕两成，当成她自己的闲置动作。两块分开，或铺开到两成以上，才算画面变了。
    """
    hot = _hot_tiles(a, b)
    if not hot:
        return False
    if _blob_fraction(hot) >= 0.20:
        return True
    return _blob_count(hot) >= 2


def _drop_echo(text: str) -> str:
    """模型有时把提示原句抄进回答。抄了就去掉，只剩叙事。"""
    cleaned = re.sub(r"(如果)?还是同一件事[，,]?只(回复|写)[「\"]?没变[」\"]?[。.]?", "", text or "")
    cleaned = re.sub(r"不要把提示抄进回答[。.]?", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned or cleaned in {"没变", "没变。"}:
        return "没变"
    return cleaned


def _is_quiet(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return bool(re.fullmatch(r"(没变|画面没变|画面基本没变|还是刚才那样)[。！!…]*", compact))


def _norm_obs(text: str) -> str:
    t = re.sub(r"[\s，。！？、…,.!]", "", text or "")
    t = t.replace("用户", "他").replace("正在", "在").replace("现在", "")
    for a, b in (
        ("玩网页", "看网页"),
        ("浏览网页", "看网页"),
        ("看一个网页", "看网页"),
        ("看某个网页", "看网页"),
        ("手在操作电脑", ""),
        ("操作电脑", ""),
        ("手在打字", ""),
        ("手在点击", ""),
    ):
        t = t.replace(a, b)
    return t


def _is_vague(text: str) -> bool:
    if _is_quiet(text):
        return False
    core = _norm_obs(text)
    for word in (
        "他在", "他", "看网页", "看页面", "看网站", "看浏览器", "看屏幕", "看电脑", "用电脑",
        "看视频", "放视频", "播视频", "看片子", "看影片",
    ):
        core = core.replace(word, "")
    return len(core) < 4


def _is_repeat(text: str, history: list[str]) -> bool:
    if _is_quiet(text):
        return True
    cur = _norm_obs(text)
    if len(cur) < 4:
        return True
    for old in history[-8:]:
        prev = _norm_obs(old)
        if not prev:
            continue
        if cur == prev or cur in prev or prev in cur:
            return True
        if len(cur) >= 6 and len(prev) >= 6:
            ga = {cur[i:i + 2] for i in range(len(cur) - 1)}
            gb = {prev[i:i + 2] for i in range(len(prev) - 1)}
            if ga and gb and len(ga & gb) / len(ga | gb) >= 0.72:
                return True
    return False


def _diff(a: bytes, b: bytes) -> float:
    if not a or not b or len(a) != len(b):
        return 999.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _clip_motion(sigs: list[bytes]) -> float:
    if len(sigs) < 2:
        return 0.0
    return sum(_diff(a, b) for a, b in zip(sigs, sigs[1:])) / (len(sigs) - 1)


def _write_clip(frames, fps: int = 2, path: Optional[Path] = None) -> Path:
    import av
    path = path or ROOT / "tmp" / "clip.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    even = []
    for im in frames:
        im = im.convert("RGB")
        w, h = im.size
        w -= w % 2
        h -= h % 2
        if w < 2 or h < 2:
            continue
        if (w, h) != im.size:
            im = im.crop((0, 0, w, h))
        even.append(im)
    if len(even) < 2:
        raise RuntimeError("片段太短")
    container = av.open(str(path), mode="w")
    stream = container.add_stream("libx264", rate=fps)
    stream.width = even[0].width
    stream.height = even[0].height
    stream.pix_fmt = "yuv420p"
    stream.options = {"preset": "ultrafast", "crf": "28"}
    try:
        for im in even:
            frame = av.VideoFrame.from_image(im).reformat(format="yuv420p")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
    return path


def _history_block(history: list[str]) -> str:
    return "\n".join(f"{i}. {item}" for i, item in enumerate(history[-8:], 1))


def _build_prompt(extra: str, history: list[str], compare: bool) -> str:
    text = DEFAULT_PROMPT
    note = (extra or "").strip()
    if note:
        text += "\n这一眼另外留意：" + note
    if not compare:
        return text
    if not history:
        return text + "\n这是第一眼。先写出他正在做的事，带上名字和画面里的一句原文。"
    lines = "\n".join(f"{i}. {item}" for i, item in enumerate(history[-8:], 1))
    return (
        text
        + "\n你刚才已经看过这些（从早到晚）：\n"
        + lines
        + "\n接着上面的叙事往下写这一眼的新重点。还是刚才那段，只写没变。不要把提示抄进回答。"
    )


def _build_watch_prompt(extra: str, history: list[str], compare: bool) -> str:
    text = WATCH_PROMPT
    scene = str(_state.get("scene") or "auto")
    text += "\n当前模式：" + SCENE_LABELS.get(scene, "自动") + "。" + SCENE_PROMPTS.get(scene, SCENE_PROMPTS["auto"])
    note = (extra or "").strip()
    if note:
        text += "\n另外留意：" + note
    if compare and history:
        text += (
            "\n上一段观察（可能有误，仅用于对比，以当前画面为准）："
            + history[-1][:100]
            + "\n本段有实质新事件才说一句，没有就只写没变。"
        )
    return text


def _move(inputs, model):
    import torch
    device = model.device
    dtype = next(model.parameters()).dtype

    def cast(value):
        if not hasattr(value, "to"):
            return value
        if isinstance(value, torch.Tensor) and value.is_floating_point():
            return value.to(device=device, dtype=dtype)
        return value.to(device)

    if hasattr(inputs, "to") and not isinstance(inputs, dict):
        try:
            return cast(inputs)
        except Exception:
            pass
    out = {}
    for key, value in dict(inputs).items():
        out[key] = cast(value) if hasattr(value, "to") else value
    return out


def _image_part(image, mode: str) -> dict:
    if mode == "image":
        return {"type": "image", "image": image}
    path = ROOT / "tmp" / "frame.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return {"type": "image", "url": str(path)}


def _apply_content(processor, parts: list, prompt: str, downsample: str, max_slice_nums: int, extra: Optional[dict] = None):
    messages = [{
        "role": "user",
        "content": list(parts) + [{"type": "text", "text": prompt}],
    }]
    template_kwargs = dict(
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
        downsample_mode=downsample,
        max_slice_nums=max_slice_nums,
        enable_thinking=False,
    )
    template_kwargs.update(extra or {})
    try:
        return processor.apply_chat_template(messages, **template_kwargs)
    except TypeError:
        proc_kw = {
            "downsample_mode": template_kwargs.pop("downsample_mode", downsample),
            "max_slice_nums": template_kwargs.pop("max_slice_nums", max_slice_nums),
        }
        for key in list(extra or {}):
            if key in template_kwargs:
                proc_kw[key] = template_kwargs.pop(key)
        template_kwargs.pop("enable_thinking", None)
        template_kwargs["processor_kwargs"] = proc_kw
        return processor.apply_chat_template(messages, **template_kwargs)


def _apply_template(processor, image, prompt: str, downsample: str, max_slice_nums: int, mode: str):
    return _apply_content(
        processor,
        [_image_part(image, mode)],
        prompt,
        downsample,
        max_slice_nums,
    )


def _apply_video(processor, path: Path, prompt: str, downsample: str, max_num_frames: int):
    # Decode explicitly: torchvision's decoder is incompatible with some PyAV
    # versions. Arrays still enter the native video processor, not image mode.
    import av
    import numpy as np

    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate or 2)
        decoded = [frame.to_ndarray(format="rgb24") for frame in container.decode(stream)]
    if not decoded:
        raise ValueError("视频没有可解码的帧")
    indices = _even(list(range(len(decoded))), max_num_frames)
    video = np.stack([decoded[index] for index in indices])
    return _apply_content(
        processor, [{"type": "video", "video": video}], prompt, downsample,
        max_slice_nums=1,
        extra={"do_sample_frames": False, "stack_frames": 1, "use_image_id": False,
               "video_metadata": [{"fps": fps, "total_num_frames": len(decoded),
                                   "duration": len(decoded) / fps, "frames_indices": indices}]},
    )


def _apply_live_video(processor, frames, timestamps, prompt, downsample):
    import numpy as np

    elapsed = max(0.001, timestamps[-1] - timestamps[0])
    fps = (len(frames) - 1) / elapsed
    return _apply_content(
        processor,
        [{"type": "video", "video": np.stack([np.asarray(im.convert("RGB")) for im in frames])}],
        f"以下是连续录屏，覆盖约{elapsed:.1f}秒，按时间从早到晚。\n" + prompt,
        downsample, max_slice_nums=1,
        extra={"do_sample_frames": False, "stack_frames": 1, "use_image_id": False,
               "video_metadata": [{"fps": fps, "total_num_frames": len(frames),
                                   "duration": elapsed + 1 / fps,
                                   "frames_indices": [round((t - timestamps[0]) * fps) for t in timestamps]}]},
    )


def _apply(processor, image, prompt: str, downsample: str, max_slice_nums: int):
    global _image_mode
    modes = [_image_mode]
    modes.append("url" if _image_mode == "image" else "image")
    last: Optional[BaseException] = None
    for mode in modes:
        try:
            inputs = _apply_template(processor, image, prompt, downsample, max_slice_nums, mode)
            _image_mode = mode
            return inputs
        except Exception as exc:
            last = exc
    assert last is not None
    raise last


def _end_stream(streamer) -> None:
    end = getattr(streamer, "end", None)
    if callable(end):
        try:
            end()
            return
        except Exception:
            pass
    try:
        streamer.text_queue.put(streamer.stop_signal)
    except Exception:
        pass


_last_profile: Dict[str, Any] = {}


_vision_mod = None


def _vision_module(model):
    global _vision_mod
    if _vision_mod is not None:
        return _vision_mod
    for name, mod in model.named_modules():
        low = name.lower()
        if low.endswith("vpm") or low.endswith("vision_tower") or low.endswith("visual"):
            _vision_mod = mod
            return mod
    return None


def _watch_vision(model, box: dict) -> list:
    target = _vision_module(model)
    if target is None:
        return []
    state = {"t": None}

    def pre(*_a, **_k):
        state["t"] = time.perf_counter()

    def post(*_a, **_k):
        if state["t"] is not None:
            box["ms"] += int((time.perf_counter() - state["t"]) * 1000)
            state["t"] = None

    return [target.register_forward_pre_hook(pre), target.register_forward_hook(post)]


def describe(
    image,
    prompt: str,
    *,
    downsample: str,
    max_slice_nums: int,
    max_new_tokens: int,
    video_path: Optional[Path] = None,
    frames: Optional[list] = None,
    video_timestamps: Optional[list] = None,
    stop_event: Optional[threading.Event] = None,
    do_sample: bool = True,
    stream: Optional[bool] = None,
    stop_on_label: bool = False,
    preface: bool = True,
) -> str:
    from transformers import StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer

    event = _stop if stop_event is None else stop_event

    global _last_profile
    model = _model
    processor = _processor
    if model is None or processor is None:
        raise RuntimeError("模型还没加载")
    prep_started = time.perf_counter()
    if video_timestamps is not None:
        if not frames or len(frames) < 2 or len(frames) != len(video_timestamps):
            raise ValueError("实时视频需要至少两帧及对应的时间戳")
        inputs = _move(_apply_live_video(processor, frames, video_timestamps, prompt, downsample), model)
    elif video_path is not None:
        inputs = _move(_apply_video(processor, video_path, prompt, downsample, max_num_frames=6), model)
    elif frames:
        lead = "这几张是原图，按时间从早到晚。每一张都要看，不要只看最后一张。\n" if preface else ""
        parts = [{"type": "image", "image": im.convert("RGB")} for im in frames]
        inputs = _move(_apply_content(
            processor,
            parts,
            lead + prompt,
            downsample,
            max_slice_nums=max_slice_nums,
        ), model)
    else:
        inputs = _move(_apply(processor, image, prompt, downsample, max_slice_nums), model)
    prep_ms = int((time.perf_counter() - prep_started) * 1000)
    profile_box: Dict[str, Any] = {}
    tok = getattr(processor, "tokenizer", processor)
    use_stream = do_sample if stream is None else bool(stream)
    id_rows = inputs["input_ids"] if isinstance(inputs, dict) else inputs.input_ids
    prompt_len = int(id_rows.shape[-1])
    # max_slice_nums=1 above means exactly one target-size row per frame.
    video_frames = len(inputs["target_sizes_videos"]) if "target_sizes_videos" in inputs else 0

    class _Halt(StoppingCriteria):
        def __init__(self) -> None:
            self.first: Optional[float] = None

        def __call__(self, input_ids, scores, **kwargs) -> bool:
            if self.first is None:
                self.first = time.perf_counter()
            if event.is_set():
                return True
            if not stop_on_label:
                return False
            new = input_ids[0, prompt_len:]
            n = int(new.shape[-1])
            if n < 2 or (n > 6 and n % 4 != 0):
                return False
            tail = tok.decode(new[-48:], skip_special_tokens=True)
            if "变化" in tail:
                after = tail.split("变化")[-1]
                if "\n" in after or len(after.strip("：: \n")) >= 2:
                    return True
            compact = re.sub(r"\s+", "", tail)
            if compact.endswith("没变") and "界面" not in tail and n <= 16:
                return True
            return False

    def _once(pass_downsample: bool) -> str:
        import torch

        halt = _Halt()
        payload = dict(inputs)
        payload.update(
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            use_cache=True,
            stopping_criteria=StoppingCriteriaList([halt]),
        )
        if do_sample:
            payload.update(temperature=0.7, top_p=0.95, top_k=100, repetition_penalty=1.03)
        if pass_downsample:
            payload["downsample_mode"] = downsample
        encode = {"ms": 0}
        hooks = _watch_vision(model, encode)
        gen_started = time.perf_counter()
        text = ""
        try:
            if use_stream:
                streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
                payload["streamer"] = streamer
                errors: list[BaseException] = []

                def _generate() -> None:
                    try:
                        with torch.inference_mode():
                            model.generate(**payload)
                    except BaseException as exc:
                        errors.append(exc)
                    finally:
                        if errors:
                            _end_stream(streamer)

                worker = threading.Thread(target=_generate, daemon=True)
                worker.start()
                parts: list[str] = []
                for piece in streamer:
                    if piece:
                        parts.append(piece)
                        publish({"type": "delta", "text": piece})
                worker.join()
                if errors:
                    raise errors[0]
                text = "".join(parts)
            else:
                with torch.inference_mode():
                    out = model.generate(**payload)
                seq = out.sequences if hasattr(out, "sequences") else out
                row = seq[0]
                new_ids = row[prompt_len:] if int(row.shape[-1]) > prompt_len else row
                text = tok.decode(new_ids, skip_special_tokens=True)
        finally:
            for hook in hooks:
                try:
                    hook.remove()
                except Exception:
                    pass
        finished = time.perf_counter()
        first = halt.first or finished
        encode_ms = int(encode["ms"])
        prefill_ms = max(0, int((first - gen_started) * 1000) - encode_ms)
        profile_box.update({
            "prep_ms": prep_ms,
            "encode_ms": encode_ms,
            "prefill_ms": prefill_ms,
            "decode_ms": int((finished - first) * 1000),
            "generate_ms": int((finished - gen_started) * 1000),
            "downsample": downsample,
            "max_new_tokens": max_new_tokens,
            "frames": video_frames if video_path is not None or video_timestamps is not None else len(frames) if frames else 1,
            "input_mode": "live_video" if video_timestamps is not None else "video" if video_path is not None else "images" if frames else "single",
            "input_tokens": prompt_len,
            "video_frames": video_frames,
        })
        return _clean(text)

    with _infer_lock:
        try:
            text = _once(True)
        except TypeError as exc:
            if "downsample_mode" not in str(exc):
                raise
            text = _once(False)
    _last_profile = dict(profile_box)
    return text


def _clamp(opts: Dict[str, Any]) -> Dict[str, Any]:
    downsample = str(opts.get("downsample") or "4x")
    if downsample not in ("16x", "4x"):
        downsample = "4x"
    try:
        monitor = int(opts.get("monitor", 1))
    except (TypeError, ValueError):
        monitor = 1
    try:
        min_gap = float(opts.get("min_gap", 0))
    except (TypeError, ValueError):
        min_gap = 0
    try:
        max_new_tokens = int(opts.get("max_new_tokens", 160))
    except (TypeError, ValueError):
        max_new_tokens = 160
    try:
        max_edge = int(opts.get("max_edge", 1920))
    except (TypeError, ValueError):
        max_edge = 1920
    try:
        max_slice_nums = int(opts.get("max_slice_nums", 9))
    except (TypeError, ValueError):
        max_slice_nums = 9
    scene = str(opts.get("scene") or "auto")
    # Compatibility with the initial video-mode selector.
    if scene == "short_video":
        scene = "video"
    if scene not in SCENE_PROMPTS:
        scene = "auto"
    return {
        "monitor": monitor,
        "capture_fps": max(1, min(int(opts.get("capture_fps", 2)), 6)),
        "window_seconds": max(2.0, min(float(opts.get("window_seconds", 4)), 6.0)),
        "prompt": str(opts.get("prompt") or ""),
        "scene": scene,
        "min_gap": max(0.0, min(min_gap, 60.0)),
        "max_new_tokens": max(16, min(max_new_tokens, 512)),
        "max_edge": max(480, min(max_edge, 2560)),
        "downsample": downsample,
        "max_slice_nums": max(1, min(max_slice_nums, 36)),
        "compare_prev": bool(opts.get("compare_prev", True)),
    }


def _finish_text(text: str, history: list[str], ms: int, preview: str) -> bool:
    if _is_quiet(text) or _is_repeat(text, history) or _is_vague(text):
        _set(last_ms=ms, message="画面没变")
        publish({"type": "same", "text": "没变", "ms": ms})
        return True
    history.append(text.replace("\n", " ")[:120])
    del history[:-8]
    _set(last_ms=ms, last_text=text, message="正在看屏幕")
    publish({"type": "done", "text": text, "ms": ms, "jpeg": preview})
    return False


def _ask(
    image,
    frames,
    prompt: str,
    sharp: str,
    opts: Dict[str, Any],
    video_path: Optional[Path] = None,
    stop_event: Optional[threading.Event] = None,
    once: bool = False,
) -> str:
    # Opt-in experiment; preserve the existing image baseline for A/B replay.
    if video_path is None and frames and os.environ.get("MINICPM_V47_INPUT_MODE") == "video":
        import tempfile

        with tempfile.TemporaryDirectory(prefix="minicpm-video-") as directory:
            selected = _even(frames, 6)
            path = _write_clip(selected, path=Path(directory) / "clip.mp4")
            return _ask(image, selected, prompt, sharp, opts, video_path=path,
                        stop_event=stop_event, once=once)
    kwargs = dict(
        downsample=opts["downsample"],
        max_slice_nums=1 if video_path is not None else (1 if frames else opts["max_slice_nums"]),
        max_new_tokens=opts["max_new_tokens"],
        video_path=video_path,
        frames=frames,
        stop_event=stop_event,
        do_sample=bool(opts.get("do_sample", True)),
        stream=opts.get("stream"),
        stop_on_label=bool(opts.get("stop_on_label", False)),
        preface=bool(opts.get("preface", True)),
    )
    try:
        text = describe(image, prompt, **kwargs)
    except Exception as exc:
        low = str(exc).lower()
        oom = "out of memory" in low or ("cuda" in low and "memory" in low)
        if not oom or (video_path is None and not frames):
            raise
        import torch
        torch.cuda.empty_cache()
        kwargs["downsample"] = "16x"
        if frames and len(frames) > 4:
            kwargs["frames"] = _even(frames, 4)
        text = describe(image, prompt, **kwargs)
    event = _stop if stop_event is None else stop_event
    if not once and _is_vague(text) and not event.is_set():
        text = describe(image, prompt + "\n" + sharp, **kwargs)
    return _drop_echo(text)


def _loop(opts: Dict[str, Any]) -> None:
    import sys
    from video_stream import run

    run(sys.modules[__name__], opts)


def _bright_enough(image) -> bool:
    gray = image.convert("L").resize((32, 18))
    return sum(gray.getdata()) / (32 * 18) >= 2


def _grab_ready(screen: _Screen):
    for _ in range(8):
        grabbed = screen.grab()
        if grabbed is not None and getattr(grabbed, "size", None) and _bright_enough(grabbed):
            return grabbed
        time.sleep(0.15)
    return None


def _glance_prompt(ask: str, along: bool) -> tuple[str, str]:
    question = (ask or "").strip()
    if along:
        extra = f"对方说：{question}。" if question else ""
        return (
            WATCH_PROMPT + extra + "用一两句讲这几秒里看得见的内容。不要只说他在看视频。",
            WATCH_SHARP,
        )
    if question:
        return (
            "对方要你看他的屏幕，只回答这一句：" + question
            + "。必须根据画面，点出看得见的名字、图标或标题，以及它在屏幕的哪一块，"
            + "例如左上、右下、任务栏、桌面第几行。看不见就说没看见。不要编，不要说去打开或去点。",
            "还是没指到位置。说出名字和大概在画面的哪一块。说不出来就只回复「没变」。",
        )
    return DEFAULT_PROMPT, SHARP_PROMPT


def _monitor_box(index: int, width: int, height: int) -> dict:
    try:
        import mss
        with mss.mss() as sct:
            mon = sct.monitors[index] if 0 < index < len(sct.monitors) else sct.monitors[1]
            return {"left": int(mon["left"]), "top": int(mon["top"]), "width": int(mon["width"]), "height": int(mon["height"])}
    except Exception:
        return {"left": 0, "top": 0, "width": width, "height": height}


def _xiaoke_boxes(width: int, height: int, monitor_index: int, *, include_observer: bool = False) -> list[tuple[int, int, int, int]]:
    """她自己的窗口。铺满屏幕的桌宠不抠，否则整屏都会被涂掉。"""
    if os.name != "nt" or width < 8 or height < 8:
        return []
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return []
    user32 = ctypes.windll.user32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
    mon = _monitor_box(monitor_index, width, height)
    boxes: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = (buf.value or "").lower()
        observer = include_observer and "minicpm-v 4.7" in title
        if "xiaoke.ai" not in title and not observer:
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        scale = 1.0
        try:
            awareness = ctypes.c_int()
            if ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness)) == 0 and awareness.value == 0:
                dpi = user32.GetDpiForWindow(hwnd) or 96
                scale = max(1.0, dpi / 96.0)
        except Exception:
            scale = 1.0
        left = int(rect.left * scale)
        top = int(rect.top * scale)
        right = int(rect.right * scale)
        bottom = int(rect.bottom * scale)
        ww, hh = right - left, bottom - top
        if ww < 40 or hh < 40:
            return True
        if not observer and ww * hh >= 0.7 * mon["width"] * mon["height"]:
            return True
        x0 = max(0, min(width, left - mon["left"]))
        y0 = max(0, min(height, top - mon["top"]))
        x1 = max(0, min(width, right - mon["left"]))
        y1 = max(0, min(height, bottom - mon["top"]))
        if x1 - x0 > 8 and y1 - y0 > 8:
            boxes.append((x0, y0, x1, y1))
        return True

    user32.EnumWindows(visit, 0)
    return boxes


def _mask_boxes(img, boxes: list[tuple[int, int, int, int]]):
    if not boxes:
        return img
    painted = img.copy()
    from PIL import ImageDraw
    draw = ImageDraw.Draw(painted)
    for box in boxes:
        draw.rectangle(box, fill=0)
    return painted


def _live_frame(image, monitor_index: int, max_edge: int):
    boxes = _xiaoke_boxes(image.width, image.height, monitor_index, include_observer=True)
    return _fit(_mask_boxes(image, boxes), max_edge)


_follow_sig: bytes | None = None


def _crop_frame(img, crop: list, mon: dict, raw_w: int, raw_h: int):
    """把已经缩小的整屏图裁成前台窗口。对不上就仍用整张。"""
    if img is None or not crop or len(crop) != 4 or raw_w < 8 or raw_h < 8:
        return img
    iw, ih = img.size
    if iw < 8 or ih < 8:
        return img
    sx = iw / float(raw_w)
    sy = ih / float(raw_h)
    left = int((int(crop[0]) - int(mon.get("left") or 0)) * sx)
    top = int((int(crop[1]) - int(mon.get("top") or 0)) * sy)
    right = int((int(crop[2]) - int(mon.get("left") or 0)) * sx)
    bottom = int((int(crop[3]) - int(mon.get("top") or 0)) * sy)
    left = max(0, min(iw - 2, left))
    top = max(0, min(ih - 2, top))
    right = max(left + 1, min(iw, right))
    bottom = max(top + 1, min(ih, bottom))
    if right - left < 40 or bottom - top < 40:
        return img
    return img.crop((left, top, right, bottom))


def _cropped(images: list, crop: list, mon: dict, raw_w: int, raw_h: int) -> tuple[list, bool]:
    if not images or not crop or len(crop) != 4:
        return images, False
    out = [_crop_frame(im, crop, mon, raw_w, raw_h) for im in images]
    used = any(a.size != b.size for a, b in zip(images, out))
    return (out if used else images), used


def _one_line(text: str) -> str:
    line = re.sub(r"\s+", " ", _clean(text)).strip(" 。")
    if not line or _label_echo(line):
        return "没变"
    return line


def _film(images: list) -> str:
    """一张图一句。按时间排开，就是这几秒的内容。"""
    opts = _clamp({
        "max_edge": 1280,
        "max_new_tokens": 64,
        "compare_prev": False,
        "max_slice_nums": 2,
        "downsample": "4x",
    })
    opts["do_sample"] = False
    opts["stream"] = False
    opts["stop_on_label"] = False
    opts["preface"] = False
    chosen = images if len(images) <= 6 else _even(images, 6)
    lines: list[str] = []
    for index, image in enumerate(chosen, 1):
        try:
            said = _ask(image, None, FILM_PROMPT, "", opts, stop_event=threading.Event(), once=True)
        except Exception:
            said = ""
        lines.append(f"第{index}张：{_one_line(said)}")
    return "\n".join(lines)


def glance_once(
    monitor: int = 1,
    ask: str = "",
    along: bool = False,
    before: str = "",
    gate: bool = False,
    infer: bool = True,
    detail: bool = False,
    crop: list | None = None,
    prompt: str = "",
    frames: int = 0,
    window_hwnd: int = 0,
) -> Dict[str, Any]:
    """把刚过去这几秒的原图一次送进去。不启动连续解说，也不去点。

    画面每半秒存一张。gate 为真时，这一段里没有真变化就回「没变」，不跑模型。
    infer 为假时只交原图，不加载、不调用本机 MiniCPM。
    """
    global _follow_sig, _reel_consumed, _reel_consumed_seq, _reel_seq, _target_processed_end
    try:
        index = int(monitor)
    except (TypeError, ValueError):
        index = 1
    after = max(0, _reel_consumed_seq - _OVERLAP_FRAMES)
    need = 1 if detail else 3
    if window_hwnd:
        window = _target_window(int(window_hwnd))
        if not window:
            return {"ok": False, "text": "", "message": "目标窗口不可读或已最小化，暂停视觉，不读取遮挡它的窗口"}
    else:
        _ensure_reel(index)
        window = _fresh_reel(after)
        if len(window) < need:
            window = _wait_reel(after, need, 0.45 if detail else 0.9)
    if not window:
        return {"ok": False, "text": "", "message": "这一眼是黑的，或没有抓到画面", "capture": _reel_mode}
    terminal_only = bool(window_hwnd and not _target_valid)
    gap = ""
    if _reel_consumed_seq and window[0][3] > _reel_consumed_seq + 1:
        gap = f"{_reel_consumed_seq + 1}-{window[0][3] - 1}"
    end_seq = window[-1][3]
    obs_id = f"screen-{end_seq}"

    def _mark() -> None:
        nonlocal_consumed = max(_reel_consumed_seq, end_seq - _OVERLAP_FRAMES)
        globals()["_reel_consumed_seq"] = nonlocal_consumed
        globals()["_reel_consumed"] = window[-1][0]

    if gate and _follow_sig is not None and not _span_changed([item[2] for item in window], _follow_sig):
        _mark()
        _follow_sig = window[-1][2]
        shot = window[-1][1]
        return {
            "ok": True,
            "text": "没变",
            "source": "screen",
            "observation_id": obs_id,
            "observed_at": window[-1][0],
            "seq_start": window[0][3],
            "seq_end": end_seq,
            "continuity_gap": gap,
            "changed": False,
            "skipped": True,
            "frames": len(window),
            "ms": 0,
            "capture": _reel_mode,
            "width": shot.size[0],
            "height": shot.size[1],
            "trace": _lab_trace([item[1] for item in window], [], ""),
        }
    detail = bool(detail)
    given = (prompt or "").strip()
    reading = bool(given) or detail
    busy = _window_busy([item[2] for item in window])
    if reading:
        budget = max(1, min(int(frames or 1), len(window), 4))
    else:
        budget = frame_budget(len(window), False, busy)
        if frames > 0:
            budget = max(1, min(int(frames), len(window)))
    picked = [window[-1]] if budget <= 1 else _even(window, budget)
    stored = [item[1] for item in picked]
    raw_w, raw_h = window[-1][1].size if window_hwnd else _reel_raw
    mon = {"left": 0, "top": 0, "width": raw_w, "height": raw_h} if window_hwnd else _monitor_box(index, raw_w or 1, raw_h or 1)
    box = [int(v) for v in crop] if crop and len(crop) == 4 and not window_hwnd else []
    captured, window_cropped = _cropped([item[1] for item in window], box, mon, raw_w, raw_h)
    stored, sent_cropped = _cropped(stored, box, mon, raw_w, raw_h)
    cropped = window_cropped or sent_cropped
    threading.Thread(target=_dump_reel, args=(stored,), daemon=True).start()
    images = list(stored) if reading else [_fit(im, 960, 2) for im in stored]
    _reel_consumed_seq = max(_reel_consumed_seq, end_seq - _OVERLAP_FRAMES)
    _reel_consumed = window[-1][0]
    _follow_sig = window[-1][2]
    if window_hwnd:
        _target_processed_end = end_seq
    question = (ask or "").strip()
    filming = not given and not (question and not gate)
    if given:
        prompt, sharp = given, ""
    elif filming:
        prompt, sharp = FILM_PROMPT, ""
    else:
        multi = "" if cropped else "按时间顺序看这些屏幕原图。不要写一共几张，不要写左侧右侧，不要把张数写进变化。\n"
        prompt, sharp = _glance_prompt(ask, along)
        prompt = multi + prompt
    if not infer:
        return {
            "ok": True,
            "text": "",
            "source": "screen",
            "observation_id": obs_id,
            "observed_at": window[-1][0],
            "seq_start": window[0][3],
            "seq_end": end_seq,
            "continuity_gap": gap,
            "changed": True,
            "skipped": False,
            "frames": len(images),
            "images": [_jpeg_b64(im, 1920, 90) if reading else _jpeg_b64(im, 960) for im in images],
            "ms": 0,
            "capture": _reel_mode,
            "width": images[-1].size[0],
            "height": images[-1].size[1],
            "trace": _lab_trace(captured, images, ""),
            "ocr_text": _game_text(images[-1]) if "英雄联盟" in given else _media_text(images[-1], "", given),
            "terminal_only": terminal_only,
        }
    # CPU OCR starts on these exact pixels while MiniCPM works on the GPU.
    ocr_job = _start_ocr(images[-1]) if "英雄联盟" in given or "陪看" in given else None
    load()
    use_frames = images if len(images) >= 2 else None
    image = images[-1]
    channel = "detail" if detail else "continuous"
    opts = _clamp({
        "max_edge": 1920,
        "max_new_tokens": 240 if given else (64 if detail else 40),
        "compare_prev": False,
        "max_slice_nums": 9 if reading else 1,
        "downsample": "4x" if reading else "16x",
    })
    opts["do_sample"] = False
    opts["stream"] = False
    opts["stop_on_label"] = not bool(given)
    opts["preface"] = False
    started = time.time()
    # 单独的停止信号。连续看上次点过停止后，全局 _stop 仍是置位的，沿用它这一眼会立刻空返回。
    if filming:
        text = _film(images)
    elif given:
        text = _ask(image, use_frames, prompt, sharp, opts, stop_event=threading.Event(), once=True)
    else:
        text = _ask(image, use_frames, prompt, sharp, opts, stop_event=threading.Event(), once=True)
        if _label_echo(text):
            text = "没变"
    ocr_lines, ocr_status = _finish_ocr(ocr_job)
    if "英雄联盟" in given:
        text = _game_text(image, text, lines=ocr_lines)
        if terminal_only:
            durable = []
            for previous in images:
                if previous is image:
                    durable.extend(line for line in text.splitlines() if line.startswith("结果："))
                else:
                    durable.extend(line for line in _game_text(previous).splitlines() if line.startswith("结果："))
            text = "\n".join(dict.fromkeys(durable)) or "没变"
    elif "陪看" in given:
        text = _media_text(image, text, given, lines=ocr_lines)
    ms = int((time.time() - started) * 1000)
    profile = dict(_last_profile)
    profile["channel"] = channel
    profile["total_ms"] = ms
    profile["ocr_status"] = ocr_status
    profile["ocr_engine"] = ",".join(sorted({str(row.get("engine") or "unknown") for row in ocr_lines})) or "none"
    _set(last_ms=ms, last_text=text, message="看完这一眼")
    done = {"type": "done", "text": text, "ms": ms}
    if _subs:
        done["jpeg"] = _jpeg_b64(images[-1], 960)
    publish(done)
    return {
        "ok": True,
        "text": text,
        "source": "screen",
        "observation_id": obs_id,
        "observed_at": window[-1][0],
        "seq_start": window[0][3],
        "seq_end": end_seq,
        "continuity_gap": gap,
        "changed": True,
        "frames": len(images),
        "channel": channel,
        "downsample": opts["downsample"],
        "slices": opts["max_slice_nums"],
        "profile": profile,
        "ms": ms,
        "capture": _reel_mode,
        "width": images[-1].size[0],
        "height": images[-1].size[1],
        "trace": _lab_trace(captured, images, prompt),
        "terminal_only": terminal_only,
    }


_screen_text_reader = None
_screen_reader_lock = threading.Lock()
_ocr_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screen-ocr")
_ocr_gate = threading.BoundedSemaphore(1)


def _get_screen_reader():
    global _screen_text_reader
    with _screen_reader_lock:
        if _screen_text_reader is None:
            import importlib.util
            source = ROOT.parents[1] / "companion" / "backend" / "app" / "modules" / "sight" / "screen_text.py"
            spec = importlib.util.spec_from_file_location("_companion_screen_text", source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _screen_text_reader = module
        return _screen_text_reader


def _start_ocr(image):
    # No unbounded queue: a slow native reader cannot accumulate old frames.
    if not _ocr_gate.acquire(blocking=False):
        return None
    try:
        future = _ocr_pool.submit(lambda frame=image.copy(): _get_screen_reader().read(frame))
        future.add_done_callback(lambda _: _ocr_gate.release())
        return future
    except Exception:
        _ocr_gate.release()
        return None


def _finish_ocr(future):
    if future is None:
        return [], "busy-or-unused"
    try:
        return future.result(timeout=.03), "ready"
    except FutureTimeout:
        return [], "pending-skipped"
    except Exception:
        return [], "failed"
_media_text_reader = None


def _media_text(image, text: str, prompt: str, *, lines=None) -> str:
    global _screen_text_reader, _media_text_reader
    kind = "movie" if "陪看电影电视剧" in prompt else "music" if "陪看音乐" in prompt else "video" if "陪看视频" in prompt else ""
    if not kind:
        return text
    try:
        import importlib.util

        folder = ROOT.parents[1] / "companion" / "backend" / "app" / "modules" / "sight"
        _get_screen_reader()
        if _media_text_reader is None:
            spec = importlib.util.spec_from_file_location("_media_ocr", folder / "media_ocr.py")
            _media_text_reader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_media_text_reader)
        if lines is None:
            lines = _screen_text_reader.read(image)
        return _media_text_reader.combine(_screen_text_reader.verify(text, lines), lines, image.size, kind)
    except Exception:
        return text
_target_reader = None
_target_lock = threading.Lock()
_target_hwnd = 0
_target_frames: list = []
_target_thread = None
_target_ready = threading.Event()
_target_valid = False
_target_processed_end = 0


def _target_window(hwnd: int) -> list:
    global _target_hwnd, _target_thread, _target_valid, _reel_consumed_seq, _follow_sig, _target_processed_end
    with _target_lock:
        if hwnd != _target_hwnd:
            _target_hwnd = hwnd
            _target_frames.clear()
            _target_ready.clear()
            _target_valid = False
            _target_processed_end = 0
            _reel_consumed_seq = 0
            _follow_sig = None
        if _target_thread is None or not _target_thread.is_alive():
            _target_thread = threading.Thread(target=_target_loop, name="target-capture", daemon=True)
            _target_thread.start()
    _target_ready.wait(1.5)
    with _target_lock:
        if not _target_frames:
            return []
        age = time.time() - _target_frames[-1][0]
        if _target_valid and age > 2:
            return []
        if not _target_valid and (age > 12 or _target_frames[-1][3] <= _target_processed_end):
            return []
        return [item for item in _target_frames if item[3] > max(0, _reel_consumed_seq - _OVERLAP_FRAMES)]


def _target_loop() -> None:
    global _target_valid, _reel_seq
    while True:
        with _target_lock:
            hwnd = _target_hwnd
        try:
            image = _capture_target(hwnd)
        except Exception:
            image = None
        with _target_lock:
            if hwnd == _target_hwnd:
                _target_valid = image is not None
                if image is not None:
                    _reel_seq += 1
                    image = _fit(image, 1920)
                    _target_frames.append((time.time(), image, _sig(image), _reel_seq))
                    del _target_frames[:-24]
                _target_ready.set()
        time.sleep(0.5)


def _capture_target(hwnd: int):
    global _target_reader
    if _target_reader is None:
        import importlib.util

        source = ROOT.parents[1] / "companion" / "backend" / "app" / "modules" / "sight" / "window_frame.py"
        if not source.is_file():
            return None
        spec = importlib.util.spec_from_file_location("_companion_window_frame", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _target_reader = module
    return _target_reader.capture(hwnd)


def _game_text(image, text: str = "", *, lines=None) -> str:
    """Optional native OCR shared with the backend; no extra GPU memory."""
    global _screen_text_reader
    try:
        _get_screen_reader()
        if lines is None:
            lines = _screen_text_reader.read(image)
        facts = _screen_text_reader.facts(lines, image_size=image.size)
        if any("继续游戏" in re.sub(r"\s+", "", str(line.get("text") or "")) for line in lines) and _model is not None:
            # Stylized end banners often defeat OCR. Read the isolated banner,
            # without offering answer choices or confusing a shop with a result.
            width, height = image.size
            banner = image.crop((int(width*.27), int(height*.20), int(width*.73), int(height*.55)))
            opts = _clamp({"max_edge": 960, "max_new_tokens": 16, "max_slice_nums": 1, "downsample": "4x"})
            opts.update(do_sample=False, stream=False, stop_on_label=False, preface=False)
            label = _ask(banner, None, "只照抄图中最大的一行字，不要解释。", "", opts, stop_event=threading.Event(), once=True)
            matched = re.fullmatch(r"[\s\"“「]*(胜利|失败|VICTORY|DEFEAT)[\s\"”」。.!]*", label, re.I)
            if matched:
                word = "胜利" if matched.group(1).upper() in {"胜利", "VICTORY"} else "失败"
                facts += "\n结果：" + word
        return "\n".join(part for part in (_screen_text_reader.verify(text, lines), facts) if part)
    except Exception:
        return text


def start_watch(opts: Dict[str, Any]) -> Dict[str, Any]:
    global _watch
    with _lock:
        if _watch is not None and _watch.is_alive():
            return {"ok": False, "message": "已经在看屏幕"}
        _stop.clear()
        cleaned = _clamp(opts)
        _state["watch_options"] = dict(cleaned)
        _state["scene"] = cleaned["scene"]
        _state["watch_revision"] = int(_state.get("watch_revision") or 0) + 1
        _watch = threading.Thread(target=_loop, args=(cleaned,), daemon=True)
        _watch.start()
    return {"ok": True, **status()}


def update_watch(opts: Dict[str, Any]) -> Dict[str, Any]:
    """Hot-swap only semantic settings; the active capture never restarts."""
    with _lock:
        if _watch is None or not _watch.is_alive():
            return {"ok": False, "message": "还没有开始连续录屏"}
        current = dict(_state.get("watch_options") or {})
        current.update({key: value for key, value in opts.items() if value is not None})
        cleaned = _clamp(current)
        for key in ("scene", "prompt", "compare_prev", "max_new_tokens"):
            current[key] = cleaned[key]
        _state["watch_options"] = current
        _state["scene"] = current["scene"]
        _state["watch_revision"] = int(_state.get("watch_revision") or 0) + 1
        _state["message"] = "已切换到" + SCENE_LABELS[current["scene"]] + "识别"
    publish({"type": "status", **status()})
    return {"ok": True, **status()}


def watch_options() -> dict[str, Any]:
    with _lock:
        return dict(_state.get("watch_options") or {}), int(_state.get("watch_revision") or 0)


def scene_cadence(scene: str) -> float:
    return float(SCENE_CADENCE_SECONDS.get(scene, SCENE_CADENCE_SECONDS["auto"]))


def stop_watch() -> Dict[str, Any]:
    _stop.set()
    _set(message="正在停下这一眼…")
    publish({"type": "status", **status()})
    return {"ok": True, **status()}
