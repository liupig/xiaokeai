"""本地 TTS：Qwen3-TTS CustomVoice（0.6B / 1.7B 可切换），PCM 分块流式。

合成跑在独立 GPU 进程里，和 SenseVoice / FastAPI 不共用解释器。
"""
from __future__ import annotations

import atexit
import asyncio
import gc
import io
import multiprocessing as mp
import os
import queue
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

from ..paths import SPEECH_DIR, current_speech_dir
from ..infer_backends import tts_framework

SAMPLE_RATE = 24000
DEFAULT_SIZE = "0.6b"

VARIANTS: Dict[str, Dict[str, Any]] = {
    "0.6b": {
        "id": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        "dir": SPEECH_DIR / "qwen3-tts-0.6b-customvoice",
        "min_bytes": 1024 * 1024 * 1024,
        "label": "0.6B",
        "gb": "1.7",
    },
    "1.7b": {
        "id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "dir": SPEECH_DIR / "qwen3-tts-1.7b-customvoice",
        "min_bytes": int(2.5 * 1024 * 1024 * 1024),
        "label": "1.7B",
        "gb": "4.2",
    },
}

QWEN_VOICES = [
    {"id": "Vivian", "label": "薇薇安（明亮少女）", "language": "Chinese"},
    {"id": "Serena", "label": "塞蕾娜（温柔女声）", "language": "Chinese"},
    {"id": "Uncle_Fu", "label": "福叔（沉稳男声）", "language": "Chinese"},
    {"id": "Dylan", "label": "迪伦（北京男声）", "language": "Chinese"},
    {"id": "Eric", "label": "艾瑞克（成都男声）", "language": "Chinese"},
    {"id": "Ryan", "label": "瑞恩（英语男声）", "language": "English"},
    {"id": "Aiden", "label": "艾登（美式男声）", "language": "English"},
    {"id": "Ono_Anna", "label": "小野安娜（日语女声）", "language": "Japanese"},
    {"id": "Sohee", "label": "素熙（韩语女声）", "language": "Korean"},
]

_VOICE_LANG = {v["id"]: v["language"] for v in QWEN_VOICES}
_VOICE_IDS = {v["id"] for v in QWEN_VOICES}

# 1.7B CustomVoice 的 instruct 才会生效；0.6B 官方会丢掉。
STYLE_PRESETS: Dict[str, Dict[str, str]] = {
    "off": {"label": "默认（不改语气）", "instruct": ""},
    "yujie": {
        "label": "清冷御姐",
        "instruct": (
            "用成熟低沉的御姐女声来说，语气清冷从容，语速偏慢，带一点俯视感，"
            "声音稳、不撒娇、不稚嫩、不做作卖萌。"
        ),
    },
    "husky": {
        "label": "磁性气声",
        "instruct": (
            "用低沉磁性、带明显气声的女声来说，像贴得很近在耳边低语，"
            "略沙略喘，性感克制，不要大声不要尖。"
        ),
    },
    "flirt": {
        "label": "温柔撩人",
        "instruct": (
            "用温柔略带笑意的女声来说，语调轻柔上扬，若有若无地撩人，"
            "声音软但不幼，不要萝莉音。"
        ),
    },
}

_lock = threading.Lock()
_model = None
_loaded_size = ""
_patched = False
_state: Dict[str, Any] = {
    "ready": False,
    "loading": False,
    "downloading": False,
    "message": "",
    "device": "",
    "size": "",
    "framework": "",
}
_mp = mp.get_context("spawn")
_spawn_lock = threading.Lock()
_in_q = None
_out_q = None
_cancel_ev = None
_proc = None
_reader = None
_waiters: Dict[str, queue.Queue] = {}
_waiters_lock = threading.Lock()
_cached_status: Optional[Dict[str, Any]] = None


def normalize_size(size: str | None) -> str:
    raw = (size or DEFAULT_SIZE).strip().lower().replace(" ", "")
    aliases = {
        "0.6": "0.6b", "06b": "0.6b", "0b6": "0.6b", "600m": "0.6b",
        "1.7": "1.7b", "17b": "1.7b", "1b7": "1.7b",
    }
    key = aliases.get(raw, raw)
    if key not in VARIANTS:
        raise ValueError(f"不支持的 Qwen 规格「{size}」，请选 0.6b 或 1.7b")
    return key


def _pkg_ok() -> bool:
    try:
        import qwen_tts  # noqa: F401
        return True
    except Exception:
        return False


def _weight_bytes(folder: Path) -> int:
    total = 0
    if not folder.is_dir():
        return 0
    for p in folder.glob("*.safetensors"):
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def _variant_dir(size: str) -> Path:
    spec = VARIANTS[size]
    return current_speech_dir() / Path(spec["dir"]).name


def _local_ready(size: str) -> bool:
    spec = VARIANTS[size]
    return _weight_bytes(_variant_dir(size)) >= spec["min_bytes"]


def _model_source(size: str) -> str:
    spec = VARIANTS[size]
    if _local_ready(size):
        return str(_variant_dir(size))
    return spec["id"]


def _status_inproc() -> Dict[str, Any]:
    gpu = False
    try:
        import torch
        gpu = bool(torch.cuda.is_available())
    except ImportError:
        pass
    sizes = {
        key: {
            "installed": _local_ready(key),
            "label": spec["label"],
            "gb": spec["gb"],
        }
        for key, spec in VARIANTS.items()
    }
    msg = _state["message"]
    if msg and "不是本地 Qwen" in msg:
        msg = ""
    if not _pkg_ok():
        msg = "未安装 qwen-tts。请用 Python 3.10+ 的后端环境执行：pip install qwen-tts qwen3-tts-streaming"
    elif not _state["ready"] and not _state["loading"] and not _state["downloading"]:
        if sizes["0.6b"]["installed"] or sizes["1.7b"]["installed"]:
            msg = msg or "权重已在本地。点「加载 / 切换规格」载入显存（首次可能要一两分钟）"
        else:
            msg = msg or "本地还没有权重。把资源包 B 选好后重启，或点「加载」下载"
    return {
        "engine": "qwen",
        "available": _pkg_ok(),
        "ready": bool(_state["ready"]),
        "loading": bool(_state["loading"]),
        "downloading": bool(_state["downloading"]),
        "gpu": gpu,
        "device": _state.get("device") or "",
        "size": _state.get("size") or _loaded_size or "",
        "framework": _state.get("framework") or "",
        "sizes": sizes,
        "message": msg,
    }


def resolve_speaker(voice: str) -> str:
    if voice in _VOICE_IDS:
        return voice
    raise ValueError(f"音色「{voice}」不被 Qwen3-TTS 支持")


def list_styles() -> list:
    items = []
    for key, spec in STYLE_PRESETS.items():
        items.append({"id": key, "label": spec["label"]})
    items.append({"id": "custom", "label": "自定义语气"})
    return items


def resolve_instruct(style: str | None = None, custom: str | None = None) -> str:
    style = (style or "").strip()
    custom = (custom or "").strip()
    if style == "custom":
        return custom
    preset = STYLE_PRESETS.get(style)
    if preset and preset.get("instruct"):
        return preset["instruct"]
    return custom


def _ensure_streaming_patch() -> None:
    global _patched
    if _patched:
        return
    import fast_tts  # noqa: F401  给 Qwen3TTSModel 挂上 generate_custom_voice_streaming
    _patched = True


def _float_to_pcm16(audio) -> bytes:
    import numpy as np
    import torch
    if torch.is_tensor(audio):
        audio = audio.detach().float().cpu().numpy()
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        return b""
    samples = np.clip(samples, -1.0, 1.0)
    return (samples * 32767.0).astype(np.int16).tobytes()


def unload() -> None:
    global _model, _loaded_size
    if _model is None:
        _loaded_size = ""
        _state["ready"] = False
        _state["size"] = ""
        return
    try:
        del _model
    except Exception:
        pass
    _model = None
    _loaded_size = ""
    _state["ready"] = False
    _state["size"] = ""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _download_variant(size: str) -> None:
    spec = VARIANTS[size]
    dest: Path = _variant_dir(size)
    dest.mkdir(parents=True, exist_ok=True)
    _state["downloading"] = True
    errors: list[str] = []

    _state["message"] = f"正在从 ModelScope 下载 Qwen3-TTS {spec['label']}（约 {spec['gb']}GB）…"
    try:
        from modelscope.hub.snapshot_download import snapshot_download as ms_download
        ms_download(spec["id"], local_dir=str(dest))
        if _local_ready(size):
            return
        errors.append("ModelScope 下载完成但权重不完整")
    except Exception as exc:
        errors.append(f"ModelScope：{exc}")

    _state["message"] = f"ModelScope 失败，改从 HuggingFace 镜像下载 {spec['label']}…"
    try:
        import os
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from huggingface_hub import snapshot_download as hf_download
        hf_download(spec["id"], local_dir=str(dest))
    except Exception as exc:
        errors.append(f"HuggingFace：{exc}")

    if not _local_ready(size):
        raise RuntimeError(
            f"下载 {spec['label']} 失败（{dest}）。" + "；".join(errors[-2:])
        )


def _load_model(size: str):
    global _model, _loaded_size
    size = normalize_size(size)
    if _model is not None and _loaded_size == size:
        return _model
    if not _pkg_ok():
        raise RuntimeError(
            "未安装 qwen-tts。请在 backend 虚拟环境执行：pip install qwen-tts qwen3-tts-streaming"
        )
    if _model is not None and _loaded_size != size:
        unload()

    spec = VARIANTS[size]
    if not _local_ready(size):
        _download_variant(size)
    _state["downloading"] = False

    import torch
    from qwen_tts import Qwen3TTSModel
    from ..infer_runtime import configure_torch_for_tts

    _ensure_streaming_patch()
    device, dtype = configure_torch_for_tts()
    _state["loading"] = True
    _state["device"] = device
    _state["size"] = size
    dtype_name = str(dtype).replace("torch.", "")
    _state["message"] = f"正在加载 Qwen3-TTS {spec['label']}（{device}，{dtype_name}）…"
    last_err: Optional[Exception] = None
    source = _model_source(size)
    for attn in ("sdpa", None):
        try:
            kwargs: Dict[str, Any] = {
                "device_map": device,
                "dtype": dtype,
            }
            if attn:
                kwargs["attn_implementation"] = attn
            _model = Qwen3TTSModel.from_pretrained(source, **kwargs)
            last_err = None
            break
        except TypeError:
            try:
                _model = Qwen3TTSModel.from_pretrained(source, device_map=device)
                last_err = None
                break
            except Exception as exc:
                last_err = exc
        except Exception as exc:
            last_err = exc
    if _model is None:
        _state["loading"] = False
        _state["message"] = str(last_err)
        raise RuntimeError(f"Qwen3-TTS {spec['label']} 加载失败：{last_err}")
    if not hasattr(_model, "generate_custom_voice_streaming"):
        _state["loading"] = False
        raise RuntimeError("未挂上流式接口。请安装：pip install qwen3-tts-streaming")
    if hasattr(_model, "eval"):
        try:
            _model.eval()
        except Exception:
            pass
    _loaded_size = size
    fw = tts_framework(device)
    if device == "cpu":
        inner = getattr(_model, "model", None)
        if inner is not None:
            try:
                compiled = torch.compile(inner, mode="reduce-overhead", dynamic=True)
                _model.model = compiled
                fw = {"name": "torch.inductor", "via": "torch.compile"}
            except Exception as exc:
                print(f"[tts] torch.compile skip: {exc}")
    _state["framework"] = fw.get("name") or ""
    _state["ready"] = True
    _state["loading"] = False
    _state["downloading"] = False
    _state["message"] = (
        f"Qwen3-TTS {spec['label']} 已加载（{device}，{dtype_name}，{fw.get('name')}）"
    )
    return _model


_TRAIL_OPEN = re.compile(r"[，、：:～~]+$")


def _speak_text(text: str) -> str:
    """半句逗号收尾会让模型接着含糊往下编，合成前改成句号。"""
    s = (text or "").strip()
    if _TRAIL_OPEN.search(s):
        return _TRAIL_OPEN.sub("。", s)
    return s


def _stream_chunks(
    text: str, speaker: str, language: str, size: str, instruct: str = "",
    cancel: Optional[threading.Event] = None,
):
    """同步生成器：产出 float PCM numpy / tensor 块。"""
    model = _load_model(size)
    kwargs = dict(
        text=_speak_text(text),
        speaker=speaker,
        language=language,
        # 库默认 12≈1 秒；2 只有约 0.17 秒，生成稍慢或经反代就会播成一字一顿
        chunk_size=8,
        max_new_tokens=512,
        non_streaming_mode=False,
    )
    if instruct.strip() and size != "0.6b":
        kwargs["instruct"] = instruct.strip()
    backends = ("faster", "dynamic") if str(_state.get("device") or "").startswith("cuda") else ("dynamic",)
    last_err: Optional[Exception] = None
    import torch
    with torch.inference_mode():
        for backend in backends:
            try:
                gen = model.generate_custom_voice_streaming(backend=backend, **kwargs)
                try:
                    for item in gen:
                        if cancel is not None and cancel.is_set():
                            return
                        yield item[0] if isinstance(item, tuple) else item
                finally:
                    try:
                        gen.close()
                    except Exception:
                        pass
                return
            except Exception as exc:
                last_err = exc
    raise RuntimeError(f"本地流式合成失败：{last_err}")


def _warmup_inproc(size: str = DEFAULT_SIZE) -> Dict[str, Any]:
    size = normalize_size(size)
    label = VARIANTS[size]["label"]
    with _lock:
        _load_model(size)
        _state["message"] = f"正在预热 {label} 本地流式（首次 CUDA Graph 可能要几十秒）…"
        try:
            for _ in _stream_chunks("你好。", "Vivian", "Chinese", size):
                pass
        except Exception as exc:
            _state["message"] = f"已加载 {label}，流式预热失败：{exc}"
            raise
    _state["ready"] = True
    _state["loading"] = False
    _state["downloading"] = False
    _state["message"] = f"Qwen3-TTS {label} 本地流式已就绪（{_state.get('device') or 'cpu'}）"
    return _status_inproc()


def _to_wav_bytes(samples, sr: int) -> bytes:
    import numpy as np
    import soundfile as sf
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.reshape(-1)
    audio = np.clip(audio, -1.0, 1.0)
    buf = io.BytesIO()
    sf.write(buf, audio, int(sr), format="WAV", subtype="PCM_16")
    return buf.getvalue()


def synthesize(text: str, voice: str = "Vivian", size: str = DEFAULT_SIZE, instruct: str = "") -> bytes:
    """整段 WAV（兼容旧调用）。优先走流式再拼接。"""
    import numpy as np
    parts = []
    for chunk in synthesize_pcm_sync(text, voice, size, instruct):
        arr = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        parts.append(arr)
    if not parts:
        raise RuntimeError("本地 TTS 未返回音频")
    return _to_wav_bytes(np.concatenate(parts), SAMPLE_RATE)


def synthesize_pcm_sync(
    text: str, voice: str = "Vivian", size: str = DEFAULT_SIZE, instruct: str = "",
    cancel: Optional[threading.Event] = None,
):
    speaker = resolve_speaker(voice)
    language = _VOICE_LANG.get(speaker, "Chinese")
    size = normalize_size(size)
    t0 = time.perf_counter()
    # 插话 abort 时，排队等锁的请求必须能退出，否则 GPU 锁会排到几十秒
    while True:
        if cancel is not None and cancel.is_set():
            return
        if _lock.acquire(timeout=0.12):
            break
    try:
        lock_ms = (time.perf_counter() - t0) * 1000
        first = True
        for audio in _stream_chunks(text, speaker, language, size, instruct, cancel):
            if cancel is not None and cancel.is_set():
                break
            pcm = _float_to_pcm16(audio)
            if pcm:
                if first:
                    first = False
                    first_ms = (time.perf_counter() - t0) * 1000
                    from .. import talk_log
                    talk_log.write(
                        "tts",
                        f"锁 {lock_ms:.0f}ms · 首包 {first_ms:.0f}ms · {len(text)}字  {text[:40]}",
                    )
                yield pcm
    finally:
        _lock.release()


def _is_tts_worker() -> bool:
    return os.environ.get("COMPANION_TTS_WORKER") == "1"


def _worker_alive() -> bool:
    return bool(_proc is not None and _proc.is_alive())


def _stop_worker() -> None:
    global _proc, _in_q, _out_q, _cancel_ev, _reader
    if _in_q is not None:
        try:
            _in_q.put(("stop",))
        except Exception:
            pass
    if _proc is not None and _proc.is_alive():
        _proc.join(timeout=3)
        if _proc.is_alive():
            _proc.terminate()
    _proc = None
    _in_q = None
    _out_q = None
    _cancel_ev = None
    _reader = None


def release() -> None:
    """当前没用本地 Qwen TTS 时卸掉 GPU 进程，把显存还回去。"""
    global _cached_status
    if _is_tts_worker():
        unload()
        return
    _stop_worker()
    _cached_status = None
    _state["ready"] = False
    _state["loading"] = False
    _state["downloading"] = False
    _state["device"] = ""
    _state["size"] = ""
    _state["framework"] = ""
    _state["message"] = "未加载（当前 TTS 不是本地 Qwen）"
    print("[tts] released worker")


def _reader_loop() -> None:
    while _out_q is not None:
        try:
            msg = _out_q.get()
        except (EOFError, OSError, ValueError):
            break
        if not msg:
            continue
        key = msg[1] if len(msg) > 1 else ""
        with _waiters_lock:
            box = _waiters.get(str(key))
        if box is not None:
            box.put(msg)


def _ensure_worker() -> None:
    global _proc, _in_q, _out_q, _cancel_ev, _reader
    if _worker_alive():
        return
    with _spawn_lock:
        if _worker_alive():
            return
        from .tts_proc import main as tts_main
        _in_q = _mp.Queue()
        _out_q = _mp.Queue(maxsize=64)
        _cancel_ev = _mp.Event()
        _proc = _mp.Process(
            target=tts_main, args=(_in_q, _out_q, _cancel_ev),
            daemon=True, name="companion-tts",
        )
        _proc.start()
        _reader = threading.Thread(target=_reader_loop, daemon=True, name="tts-rpc-reader")
        _reader.start()
        print(f"[tts] worker pid={_proc.pid}")
        atexit.register(_stop_worker)


def _waiter(key: str) -> queue.Queue:
    box: queue.Queue = queue.Queue()
    with _waiters_lock:
        _waiters[key] = box
    return box


def _drop_waiter(key: str) -> None:
    with _waiters_lock:
        _waiters.pop(key, None)


def status() -> Dict[str, Any]:
    if _is_tts_worker():
        return _status_inproc()
    global _cached_status
    if _cached_status:
        st = dict(_cached_status)
        st["process"] = "tts-worker"
        st["pid"] = int(_proc.pid or 0) if _proc else 0
        return st
    return _status_inproc()


def warmup(size: str = DEFAULT_SIZE, *, download: bool = False) -> Dict[str, Any]:
    size = normalize_size(size)
    if not _pkg_ok():
        raise RuntimeError("未安装 qwen-tts")
    if not download and not _local_ready(size):
        raise FileNotFoundError(f"本地没有 Qwen3-TTS {VARIANTS[size]['label']} 权重")
    if _is_tts_worker():
        return _warmup_inproc(size)
    _ensure_worker()
    box = _waiter("warmup")
    try:
        _in_q.put(("warmup", size))
        kind, _, payload = box.get(timeout=300)
    finally:
        _drop_waiter("warmup")
    if kind != "ok":
        raise RuntimeError(str(payload))
    global _cached_status
    _cached_status = dict(payload)
    _cached_status["process"] = "tts-worker"
    _cached_status["pid"] = int(_proc.pid or 0) if _proc else 0
    _state["ready"] = True
    _state["message"] = _cached_status.get("message") or ""
    return status()


async def synthesize_pcm(
    text: str, voice: str, size: str = DEFAULT_SIZE, instruct: str = "",
    cancel: Optional[threading.Event] = None,
) -> AsyncIterator[bytes]:
    """边生成边产出 PCM。合成在独立 GPU 进程；客户端断开只杀这一段。"""
    if _is_tts_worker():
        # 子进程里不会走这条；留给误用时的兜底
        for pcm in synthesize_pcm_sync(text, voice, size, instruct, cancel):
            yield pcm
        return
    _ensure_worker()
    job = uuid.uuid4().hex
    stop = cancel if cancel is not None else threading.Event()
    box = _waiter(job)
    _in_q.put(("synth", job, text, voice, size, instruct))
    first_limit = 40.0
    chunk_limit = 25.0
    t_wait = time.perf_counter()
    got = False
    try:
        while True:
            if stop.is_set():
                _in_q.put(("cancel", job))
                return
            try:
                msg = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: box.get(timeout=0.2),
                )
            except queue.Empty:
                if not _worker_alive():
                    raise RuntimeError("TTS 进程已退出")
                limit = chunk_limit if got else first_limit
                if (time.perf_counter() - t_wait) > limit:
                    stop.set()
                    try:
                        _in_q.put(("cancel", job))
                    except Exception:
                        pass
                    raise RuntimeError(
                        "本地 TTS 超时。显存可能被其它残留 python 占满，"
                        "请关掉旧的开发后端或任务管理器里无主 python.exe 后再试。"
                    )
                continue
            kind = msg[0]
            if kind == "pcm":
                if stop.is_set():
                    _in_q.put(("cancel", job))
                    return
                yield msg[2]
                got = True
                t_wait = time.perf_counter()
            elif kind == "err":
                raise RuntimeError(str(msg[2]))
            else:
                if not got:
                    raise RuntimeError("本地 TTS 未返回音频")
                return
    finally:
        if stop.is_set():
            try:
                _in_q.put(("cancel", job))
            except Exception:
                pass
        _drop_waiter(job)
