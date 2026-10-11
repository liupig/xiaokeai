"""MiniCPM-o 4.5 推理：优先 GGUF Q4（llama-omni-server），否则独立 PyTorch int4/AWQ。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

# llama-server 只走 loopback。系统代理（Clash 等）会把 127.0.0.1 劫持成空 502。
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import numpy as np

OMNI_URL = "http://127.0.0.1:9060"
# 1 = 只听+说，不加载视觉编码器（约省 1GB）
MEDIA_TYPE = 1
_TURN_PROMPTS = {
    "voice_clone_prompt": "<|im_start|>system\n模仿音频样本的音色并生成新的内容。\n<|audio_start|>",
    "assistant_prompt": (
        "<|audio_end|>你的任务是用这种声音模式来当一个助手。请认真、高质量地回复用户的问题。"
        "请用高自然度的方式和用户聊天。你是由面壁智能开发的人工智能助手：面壁小钢炮。"
        "<|im_end|>\n<|im_start|>user\n"
    ),
}

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
ASSETS = ROOT / "assets"
BIN = ROOT / "bin"
TMP = ROOT / "tmp"
OUTPUT = ROOT / "output"
GGUF_DIR = MODELS / "MiniCPM-o-4_5-gguf"
AWQ_DIR = MODELS / "MiniCPM-o-4_5-AWQ"
PT_DIR = MODELS / "MiniCPM-o-4_5"
LLM_Q4 = GGUF_DIR / "MiniCPM-o-4_5-Q4_K_M.gguf"

IN_SR = 16000
OUT_SR = 24000

_lock = threading.Lock()
_backend = ""
_state: Dict[str, Any] = {
    "backend": "",
    "ready": False,
    "loading": False,
    "message": "未加载",
}

# pytorch
_model = None
_history: list = []
_ref = None

# gguf
_proc: Optional[subprocess.Popen] = None
_log_fp = None
_cnt = 1
_round = 0


def status() -> Dict[str, Any]:
    st = dict(_state)
    st["gguf_ok"] = LLM_Q4.is_file()
    st["awq_ok"] = (AWQ_DIR / "config.json").is_file() or any(AWQ_DIR.glob("*.safetensors"))
    st["pt_ok"] = (PT_DIR / "config.json").is_file()
    st["server"] = str(_find_server() or "")
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            st["cuda"] = f"{free/1024**3:.1f} / {total/1024**3:.1f} GB 空闲"
        else:
            st["cuda"] = "无 CUDA"
    except Exception:
        st["cuda"] = "未装 torch"
    return st


def _find_server() -> Optional[Path]:
    names = (
        "llama-omni-server.exe",
        "llama-server.exe",
        "llama-omni-server",
        "llama-server",
    )
    env = (os.environ.get("LLAMA_OMNI_SERVER") or "").strip()
    cands: list[Path] = []
    if env:
        cands.append(Path(env))
    for name in names:
        cands.append(BIN / name)
    cands.append(BIN / "comni" / "_internal" / "resources" / "build" / "bin" / "Release" / "llama-server.exe")
    which = (
        shutil.which("llama-omni-server")
        or shutil.which("llama-omni-server.exe")
        or shutil.which("llama-server")
        or shutil.which("llama-server.exe")
    )
    if which:
        cands.append(Path(which))
    home = os.environ.get("LOCALAPPDATA") or ""
    if home:
        cands.extend(Path(home).glob("Programs/Comni/**/llama-omni-server.exe"))
        cands.extend(Path(home).glob("Programs/Comni/**/llama-server.exe"))
        cands.extend(Path(home).glob("Comni/**/llama-omni-server.exe"))
        cands.extend(Path(home).glob("Comni/**/llama-server.exe"))
    for p in cands:
        if p.is_file():
            return p
    return None


def _gpu_total_gb() -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        )
        return float(out.strip().splitlines()[0]) / 1024.0
    except Exception:
        return 0.0


def _stop_llama_server() -> None:
    global _proc, _log_fp
    if _proc is not None and _proc.poll() is None:
        try:
            _proc.terminate()
            _proc.wait(timeout=8)
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
    _proc = None
    if _log_fp is not None:
        try:
            _log_fp.close()
        except Exception:
            pass
        _log_fp = None
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "llama-server.exe"],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
    deadline = time.time() + 20
    while time.time() < deadline:
        if not _cpp_healthy():
            return
        time.sleep(0.4)


def _cpp_json(path: str, payload: Dict[str, Any], timeout: float = 120) -> tuple[int, str]:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OMNI_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        return int(exc.code), body
    except Exception as exc:
        return 0, str(exc)


def _cpp_healthy() -> bool:
    import httpx
    try:
        r = httpx.get(f"{OMNI_URL}/health", timeout=2, trust_env=False)
        return r.status_code == 200
    except Exception:
        return False


def _reset_turn_session() -> None:
    global _cnt
    _cpp_json("/v1/stream/break", {"reason": "new_turn"}, timeout=10)
    time.sleep(0.1)
    body: Dict[str, Any] = {
        "media_type": MEDIA_TYPE,
        "duplex_mode": False,
        **_TURN_PROMPTS,
    }
    ref = _ensure_ref_wav()
    if ref.is_file() and ref.stat().st_size > 1000:
        body["voice_audio"] = str(ref)
    code, text = _cpp_json("/v1/stream/update_session_config", body, timeout=90)
    if code != 200:
        print(f"[gguf] update_session_config {code}: {text[:200]}")
    _cnt = 0


def _ensure_ref_wav() -> Path:
    dest = ASSETS / "ref.wav"
    official = (
        BIN / "comni" / "_internal" / "resources" / "apps" / "assets" / "ref_audio" / "ref_minicpm_signature.wav"
    )
    if official.is_file() and (not dest.is_file() or dest.stat().st_size < official.stat().st_size):
        ASSETS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(official, dest)
    return dest


def _ref_audio():
    import librosa
    path = ASSETS / "ref.wav"
    if path.is_file() and path.stat().st_size > 1000:
        audio, _ = librosa.load(str(path), sr=IN_SR, mono=True)
        return audio, str(path)
    return np.zeros(IN_SR, dtype=np.float32), ""


def write_wav16(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(np.rint(samples.astype(np.float32) * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(IN_SR)
        wf.writeframes(pcm.tobytes())


def f32_to_s16le(samples: np.ndarray) -> bytes:
    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    return np.clip(np.rint(x * 32767), -32768, 32767).astype("<i2").tobytes()


def _pick_pt_source() -> str:
    if (AWQ_DIR / "config.json").is_file():
        return str(AWQ_DIR)
    if (PT_DIR / "config.json").is_file():
        return str(PT_DIR)
    return "openbmb/MiniCPM-o-4_5"


def load_pytorch() -> None:
    global _model, _backend, _ref, _history
    import torch
    from transformers import AutoModel

    _state["loading"] = True
    _state["message"] = "正在加载 MiniCPM-o（独立 PyTorch，不碰 companion）…"
    src = _pick_pt_source()
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    kwargs: Dict[str, Any] = {
        "trust_remote_code": True,
        "attn_implementation": "sdpa",
        "torch_dtype": dtype,
        "init_vision": True,
        "init_audio": True,
        "init_tts": True,
    }
    last = None
    model = None
    # 先试 4bit，显存大概 11GB；失败再全精度
    try:
        from transformers import BitsAndBytesConfig
        kwargs4 = dict(kwargs)
        kwargs4.pop("torch_dtype", None)
        kwargs4["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            bnb_4bit_quant_type="nf4",
        )
        kwargs4["device_map"] = "auto"
        model = AutoModel.from_pretrained(src, **kwargs4)
        _state["message"] = "已用 bitsandbytes 4bit 加载"
    except Exception as exc:
        last = exc
        print(f"[pt] 4bit 失败，改用 {dtype}：{exc}")
    if model is None:
        kwargs["device_map"] = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            model = AutoModel.from_pretrained(src, **kwargs)
        except Exception as exc:
            raise RuntimeError(f"PyTorch 加载失败：{exc}；4bit 错误：{last}") from exc
    if torch.cuda.is_available() and hasattr(model, "cuda") and not hasattr(model, "hf_device_map"):
        model = model.eval().cuda()
    else:
        model.eval()
    if hasattr(model, "init_tts"):
        model.init_tts()
    _model = model
    _ref, _ = _ref_audio()
    _history = []
    _backend = "pytorch"
    _state.update(backend="pytorch", ready=True, loading=False, message="PyTorch MiniCPM-o 就绪")


def _sys_msg():
    ref, path = _ref_audio()
    return {
        "role": "system",
        "content": [
            "模仿输入音频中的声音特征。" if path else "用自然中文口语回答。",
            ref,
            "你是虚拟陪伴。用一两句口语中文回答，不要 markdown，不要列表。",
        ],
    }


def turn_pytorch(audio: np.ndarray, image=None) -> Iterator[Dict[str, Any]]:
    global _history
    assert _model is not None
    user_content: list = []
    omni = image is not None
    if image is not None:
        user_content.append(image)
    user_content.append(np.asarray(audio, dtype=np.float32).reshape(-1))
    msgs = [_sys_msg(), *_history, {"role": "user", "content": user_content}]
    out_wav = OUTPUT / "reply.wav"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        msgs=msgs,
        max_new_tokens=256,
        do_sample=True,
        temperature=0.7,
        use_tts_template=True,
        enable_thinking=False,
        omni_mode=omni,
        generate_audio=True,
        output_audio_path=str(out_wav),
        max_slice_nums=1,
    )
    res = _model.chat(**kwargs)
    text = res if isinstance(res, str) else str(res or "")
    if text:
        yield {"type": "text", "delta": text}
        _history.append({"role": "user", "content": "（语音）"})
        _history.append({"role": "assistant", "content": text})
        _history = _history[-6:]
    if out_wav.is_file():
        import soundfile as sf
        wav, sr = sf.read(str(out_wav), dtype="float32")
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        yield {"type": "audio", "rate": int(sr), "pcm": f32_to_s16le(wav)}
    yield {"type": "done", "text": text, "backend": "pytorch"}


def start_gguf() -> None:
    global _proc, _cnt, _backend, _log_fp
    import json as _json
    import urllib.error
    import urllib.request

    import httpx

    exe = _find_server()
    if exe is None:
        raise RuntimeError(
            "找不到 llama-server。把 Comni 装到 bin\\comni，或把 llama-server.exe 放到 "
            f"{BIN} ，或设置环境变量 LLAMA_OMNI_SERVER。"
        )
    if not LLM_Q4.is_file():
        raise RuntimeError(f"缺少 {LLM_Q4}，先运行 python download.py gguf")
    TMP.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    vram = _gpu_total_gb()
    # 听+说全 GPU；不加载视觉。短 ctx + Q4 KV 给 8GB 卡留余量。
    ngl = 99
    ctx = 1024
    t2w = "gpu:0"
    tts_layers = 100
    _stop_llama_server()
    _state["message"] = f"启动听+说 GPU llama-server（media={MEDIA_TYPE}, ngl={ngl}, ctx={ctx}, kv=q4, tts={tts_layers}）…"
    flags = {}
    if os.name == "nt":
        flags["creationflags"] = 0x08000000
    log_path = OUTPUT / "llama-server.log"
    _log_fp = open(log_path, "w", encoding="utf-8", errors="replace")
    _proc = subprocess.Popen(
        [
            str(exe), "--host", "127.0.0.1", "--port", "9060",
            "--model", str(LLM_Q4),
            "--n-gpu-layers", str(ngl),
            "--ctx-size", str(ctx),
            "--flash-attn", "on",
            "--cache-type-k", "q4_0",
            "--cache-type-v", "q4_0",
            "--batch-size", "512",
            "--ubatch-size", "256",
            "--repeat-penalty", "1.05",
            "--temp", "0.7",
        ],
        cwd=str(exe.parent),
        stdout=_log_fp,
        stderr=subprocess.STDOUT,
        **flags,
    )
    t0 = time.time()
    while time.time() - t0 < 180:
        if _proc.poll() is not None:
            raise RuntimeError("llama-server 启动后立刻退出，多半是显存不够")
        if _cpp_healthy():
            time.sleep(2)
            break
        time.sleep(1)
    else:
        raise RuntimeError("llama-server 启动超时")
    ref_path = _ensure_ref_wav()
    payload = {
        "media_type": MEDIA_TYPE,
        "use_tts": True,
        "duplex_mode": False,
        "model_dir": str(GGUF_DIR),
        "tts_bin_dir": str(GGUF_DIR / "tts"),
        "tts_gpu_layers": tts_layers,
        "token2wav_device": t2w,
        "output_dir": str(OUTPUT),
    }
    if ref_path.is_file() and ref_path.stat().st_size > 1000:
        payload["voice_audio"] = str(ref_path)
    # Windows 上 httpx 第一次 POST 可能 502，改用 urllib
    last_err = ""
    ok = False
    data = _json.dumps(payload).encode("utf-8")
    for _attempt in range(3):
        req = urllib.request.Request(
            "http://127.0.0.1:9060/v1/stream/omni_init",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = resp.read().decode("utf-8", "replace")
                if resp.status == 200:
                    ok = True
                    break
                last_err = body[:300]
        except Exception as exc:
            last_err = str(exc)
        time.sleep(2)
    if not ok:
        raise RuntimeError(f"omni_init 失败：{last_err}")
    _cnt = 1
    _backend = "gguf"
    msg = f"GGUF Q4 听+说 GPU 就绪（media={MEDIA_TYPE}, ngl={ngl}, ctx={ctx}, kv=q4, tts_gpu={tts_layers}, t2w={t2w}）"
    _state.update(backend="gguf", ready=True, loading=False, message=msg)


def turn_gguf(audio: np.ndarray, image=None) -> Iterator[Dict[str, Any]]:
    global _cnt, _round
    import httpx
    from PIL import Image

    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    # C++ 最少约 1600 sample；turn-based 整段一次 prefill，不要按秒切块
    if len(samples) < 1600:
        samples = np.pad(samples, (0, 1600 - len(samples)))
    TMP.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    _reset_turn_session()

    if image is not None and MEDIA_TYPE >= 2:
        img_path = TMP / f"frame_{_cnt}.jpg"
        image.convert("RGB").save(img_path, quality=85)
        code, text = _cpp_json("/v1/stream/prefill", {
            "audio_path_prefix": "",
            "img_path_prefix": str(img_path),
            "cnt": _cnt,
        }, timeout=120)
        if code != 200:
            yield {"type": "error", "message": f"prefill 图片失败（HTTP {code}）：{(text or '').strip()[:200]}"}
            return
        _cnt += 1

    wav = TMP / f"turn_{_cnt}.wav"
    write_wav16(wav, samples)
    code, text = _cpp_json("/v1/stream/prefill", {
        "audio_path_prefix": str(wav),
        "img_path_prefix": "",
        "cnt": _cnt,
    }, timeout=120)
    if code != 200:
        yield {"type": "error", "message": f"prefill 失败（HTTP {code}）：{(text or '').strip()[:240]}"}
        return
    _cnt += 1

    round_idx = _round
    before = time.time()
    text_out = ""
    sent_wav: set[str] = set()

    def _yield_wavs():
        newest = []
        if OUTPUT.is_dir():
            newest = sorted(
                (
                    p for p in OUTPUT.rglob("wav_*.wav")
                    if p.stat().st_mtime >= before - 1 and str(p) not in sent_wav
                ),
                key=lambda p: (p.stat().st_mtime, p.name),
            )
        import soundfile as sf
        for wav_out in newest:
            try:
                arr, sr = sf.read(str(wav_out), dtype="float32")
            except Exception:
                continue
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            if arr.size == 0:
                continue
            sent_wav.add(str(wav_out))
            yield {"type": "audio", "rate": int(sr), "pcm": f32_to_s16le(arr)}

    def _tts_done() -> bool:
        flags = list(OUTPUT.rglob("generation_done.flag")) if OUTPUT.is_dir() else []
        return any(p.stat().st_mtime >= before - 1 for p in flags)

    with httpx.Client(trust_env=False, timeout=180) as client:
        with client.stream(
            "POST", f"{OMNI_URL}/v1/stream/decode",
            json={"stream": True, "round_idx": round_idx, "debug_dir": str(OUTPUT)},
        ) as resp:
            if resp.status_code != 200:
                body = ""
                try:
                    body = resp.read().decode("utf-8", "replace")[:200]
                except Exception:
                    pass
                yield {"type": "error", "message": f"decode 失败（HTTP {resp.status_code}）：{body}"}
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                s = line.decode("utf-8", "replace") if isinstance(line, bytes) else line
                if not s.startswith("data:"):
                    continue
                data = s[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue
                piece = ev.get("content") or ""
                if piece:
                    text_out += piece
                    yield {"type": "text", "delta": piece}
                yield from _yield_wavs()

    # Token2Wav 在 8GB 上走 CPU，wav 往往比文字晚几秒才落盘
    t_wait = time.time()
    while time.time() - t_wait < 90:
        yield from _yield_wavs()
        if _tts_done():
            yield from _yield_wavs()
            break
        time.sleep(0.2)
    else:
        yield from _yield_wavs()
    _round = round_idx + 1
    yield {"type": "done", "text": text_out, "backend": "gguf"}


def warmup(prefer: str = "auto") -> Dict[str, Any]:
    with _lock:
        if _state.get("ready"):
            return status()
        _state["loading"] = True
        prefer = (prefer or "auto").lower()
        try:
            if prefer in ("gguf",) or (prefer == "auto" and _find_server() and LLM_Q4.is_file()):
                start_gguf()
            else:
                load_pytorch()
        except Exception as exc:
            if prefer == "auto":
                print(f"[warmup] 第一选择失败，改 PyTorch：{exc}")
                _state["message"] = f"改走 PyTorch：{exc}"
                load_pytorch()
            else:
                _state["loading"] = False
                _state["message"] = str(exc)
                raise
        return status()


def infer(audio: np.ndarray, image=None) -> Iterator[Dict[str, Any]]:
    if not _state.get("ready"):
        warmup("auto")
    with _lock:
        if _backend == "gguf":
            yield from turn_gguf(audio, image)
        else:
            yield from turn_pytorch(audio, image)
