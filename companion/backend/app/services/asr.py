"""本地 ASR：sherpa-onnx SenseVoice-Small INT8。识别跑在独立 CPU 进程里。"""
from __future__ import annotations

import atexit
import io
import multiprocessing as mp
import tarfile
import threading
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any, Dict, Optional

from ..paths import SPEECH_DIR

SENSEVOICE_DIR = SPEECH_DIR / "sensevoice"
MODEL_FILE = SENSEVOICE_DIR / "model.int8.onnx"
TOKENS_FILE = SENSEVOICE_DIR / "tokens.txt"
_MIN_ONNX_BYTES = 100 * 1024 * 1024

# 优先 ModelScope（国内），再试 GitHub / Hugging Face
_MODELSCOPE_IDS = [
    "chriscrs/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
]
_TAR_URLS = [
    "https://ghfast.top/https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2",
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2",
]
_FILE_MIRRORS = [
    "https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/resolve/main/",
    "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/resolve/main/",
]

_lock = threading.Lock()
_rpc_lock = threading.Lock()
_recognizer = None
_ctx = mp.get_context("spawn")
_in_q = None
_out_q = None
_proc = None
_state: Dict[str, Any] = {
    "ready": False,
    "downloading": False,
    "progress": 0.0,
    "message": "",
    "pid": 0,
}


def _model_ready() -> bool:
    return (
        MODEL_FILE.is_file()
        and TOKENS_FILE.is_file()
        and MODEL_FILE.stat().st_size >= _MIN_ONNX_BYTES
    )


def status() -> Dict[str, Any]:
    installed = _model_ready()
    sherpa_ok = True
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        sherpa_ok = False
    msg = _state["message"]
    if not sherpa_ok:
        msg = "未安装 sherpa-onnx，请在后端目录执行 pip install sherpa-onnx"
    elif not installed and not _state["downloading"]:
        msg = msg or "模型未下载（约 230MB），点「准备模型」或首次识别时自动拉取"
    return {
        "engine": "sensevoice",
        "installed": installed,
        "ready": bool(_worker_alive()) or bool(_recognizer) or (installed and sherpa_ok),
        "downloading": bool(_state["downloading"]),
        "progress": float(_state["progress"]),
        "message": msg,
        "available": sherpa_ok,
        "pid": int(_state.get("pid") or 0),
        "process": "asr-worker" if _worker_alive() else "in-process",
    }


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "CompanionStudio/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                _state["progress"] = min(0.95, done / total)
    tmp.replace(dest)


def _extract_tar(archive: Path) -> None:
    SENSEVOICE_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            if name in ("model.int8.onnx", "tokens.txt") and member.isfile():
                src = tar.extractfile(member)
                if src is None:
                    continue
                (SENSEVOICE_DIR / name).write_bytes(src.read())


def _download_modelscope() -> None:
    from modelscope.hub.snapshot_download import snapshot_download
    import shutil

    for mid in _MODELSCOPE_IDS:
        _state["message"] = f"从 ModelScope 下载 {mid}"
        src = Path(snapshot_download(mid))
        for name in ("model.int8.onnx", "tokens.txt"):
            hits = list(src.rglob(name))
            if hits:
                shutil.copy2(hits[0], SENSEVOICE_DIR / name)
        if _model_ready():
            return


def ensure_model(download: bool = True) -> None:
    """确保 INT8 模型在本地。"""
    if _model_ready():
        return
    if not download:
        raise FileNotFoundError("SenseVoice 模型不存在")
    with _lock:
        if _model_ready():
            return
        _state["downloading"] = True
        _state["progress"] = 0.0
        _state["message"] = "正在下载 SenseVoice INT8…"
        try:
            last_err: Optional[Exception] = None
            SENSEVOICE_DIR.mkdir(parents=True, exist_ok=True)
            try:
                _download_modelscope()
            except Exception as exc:
                last_err = exc
            tar_path = SPEECH_DIR / "sensevoice.tar.bz2"
            if not _model_ready():
                for url in _TAR_URLS:
                    try:
                        _state["message"] = f"下载 {url.split('/')[-1]}"
                        _download(url, tar_path)
                        _extract_tar(tar_path)
                        tar_path.unlink(missing_ok=True)
                        last_err = None
                        break
                    except Exception as exc:
                        last_err = exc
            if not _model_ready():
                for base in _FILE_MIRRORS:
                    try:
                        _state["message"] = "从镜像拉取 model.int8.onnx"
                        _download(base + "model.int8.onnx", MODEL_FILE)
                        _download(base + "tokens.txt", TOKENS_FILE)
                        last_err = None
                        break
                    except Exception as exc:
                        last_err = exc
            if not _model_ready():
                raise RuntimeError(f"SenseVoice 下载失败：{last_err}")
            _state["message"] = "模型已就绪"
            _state["progress"] = 1.0
        except Exception as exc:
            _state["message"] = str(exc)
            raise
        finally:
            _state["downloading"] = False


def _get_recognizer():
    global _recognizer
    if _recognizer is not None:
        return _recognizer
    try:
        import sherpa_onnx
    except ImportError as exc:
        raise RuntimeError("未安装 sherpa-onnx，请执行 pip install sherpa-onnx") from exc
    ensure_model(download=True)
    with _lock:
        if _recognizer is not None:
            return _recognizer
        try:
            _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(MODEL_FILE),
                tokens=str(TOKENS_FILE),
                num_threads=2,
                use_itn=True,
                language="auto",
                provider="cpu",
            )
        except TypeError:
            try:
                _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=str(MODEL_FILE),
                    tokens=str(TOKENS_FILE),
                    num_threads=2,
                    use_itn=True,
                    language="auto",
                )
            except TypeError:
                _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=str(MODEL_FILE),
                    tokens=str(TOKENS_FILE),
                    num_threads=2,
                    use_itn=True,
                )
        _state["ready"] = True
        _state["message"] = "SenseVoice 已加载（CPU）"
        return _recognizer


def _worker_alive() -> bool:
    return bool(_proc is not None and _proc.is_alive())


def _stop_worker() -> None:
    global _proc, _in_q, _out_q
    if _in_q is not None:
        try:
            _in_q.put(("stop",))
        except Exception:
            pass
    if _proc is not None and _proc.is_alive():
        _proc.join(timeout=2)
        if _proc.is_alive():
            _proc.terminate()
    _proc = None
    _in_q = None
    _out_q = None
    _state["pid"] = 0


def _ensure_worker() -> None:
    global _proc, _in_q, _out_q
    if _worker_alive():
        return
    ensure_model(download=True)
    with _lock:
        if _worker_alive():
            return
        from .asr_proc import main as asr_main
        _in_q = _ctx.Queue()
        _out_q = _ctx.Queue()
        _proc = _ctx.Process(target=asr_main, args=(_in_q, _out_q), daemon=True, name="companion-asr")
        _proc.start()
        kind, _, payload = _out_q.get(timeout=120)
        if kind != "ready":
            _stop_worker()
            raise RuntimeError(f"ASR 进程启动失败：{payload}")
        _state["pid"] = int(_proc.pid or 0)
        _state["ready"] = True
        _state["message"] = f"SenseVoice 已加载（独立 CPU 进程 pid={_proc.pid}）"
        print(f"[asr] worker pid={_proc.pid}")
        atexit.register(_stop_worker)


def warmup() -> Dict[str, Any]:
    import os
    if os.environ.get("COMPANION_ASR_WORKER") == "1":
        _get_recognizer()
        _state["ready"] = True
        _state["downloading"] = False
        _state["message"] = "SenseVoice 已加载（CPU）"
        return status()
    _ensure_worker()
    return status()


def _transcribe_local(wav_bytes: bytes) -> str:
    samples, sr = wav_bytes_to_float(wav_bytes)
    samples = _resample(samples, sr, 16000)
    rec = _get_recognizer()
    with _lock:
        stream = rec.create_stream()
        stream.accept_waveform(16000, samples)
        rec.decode_stream(stream)
        text = (stream.result.text or "").strip()
    if "|>" in text:
        text = text.split("|>")[-1].strip()
    return text


def transcribe(wav_bytes: bytes) -> str:
    import os
    if os.environ.get("COMPANION_ASR_WORKER") == "1":
        return _transcribe_local(wav_bytes)
    _ensure_worker()
    job = uuid.uuid4().hex
    with _rpc_lock:
        _in_q.put(("transcribe", job, wav_bytes))
        kind, jid, payload = _out_q.get(timeout=45)
    if kind == "ok" and jid == job:
        return payload
    if kind == "err":
        raise RuntimeError(payload)
    raise RuntimeError("ASR 进程返回异常")


def _resample(samples, src_rate: int, dst_rate: int = 16000):
    import numpy as np
    if src_rate == dst_rate or samples.size == 0:
        return samples.astype(np.float32)
    n_dst = max(1, int(round(samples.size * dst_rate / src_rate)))
    x_old = np.linspace(0.0, 1.0, samples.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_dst, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def wav_bytes_to_float(data: bytes):
    import numpy as np
    with wave.open(io.BytesIO(data), "rb") as wf:
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if sw == 2:
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        pcm = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        pcm = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)
    return pcm, sr
