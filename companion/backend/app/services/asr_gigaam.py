"""GigaAM-v3 Russian offline recognition using sherpa-onnx."""
from __future__ import annotations

import threading
from . import asr
from ..infer_runtime import cpu_infer_threads
from ..paths import SPEECH_DIR

MODEL_DIR = SPEECH_DIR / "gigaam-v3"
FILES = ("encoder.int8.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt")
BASES = (
    "https://hf-mirror.com/csukuangfj/sherpa-onnx-nemo-transducer-punct-giga-am-v3-russian-2025-12-16/resolve/main/",
    "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-transducer-punct-giga-am-v3-russian-2025-12-16/resolve/main/",
)
_lock = threading.Lock()
_recognizer = None

def model_ready():
    return all((MODEL_DIR / name).is_file() and (MODEL_DIR / name).stat().st_size > 0 for name in FILES) and (MODEL_DIR / FILES[0]).stat().st_size > 100 * 1024 * 1024

def ensure_model(download=True):
    if model_ready():
        return
    if not download:
        raise FileNotFoundError("GigaAM-v3 model is not installed")
    with _lock:
        if model_ready():
            return
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        asr._state.update(downloading=True, message="Downloading GigaAM-v3 (Russian)…")
        try:
            for name in FILES:
                path = MODEL_DIR / name
                minimum = 100 * 1024 * 1024 if name == FILES[0] else 1
                if path.is_file() and path.stat().st_size >= minimum:
                    continue
                error = None
                for base in BASES:
                    try:
                        asr._download(base + name, path)
                        error = None
                        break
                    except Exception as exc:
                        error = exc
                if error:
                    raise RuntimeError(f"GigaAM-v3 download failed: {name}: {error}") from error
            if not model_ready():
                raise RuntimeError("GigaAM-v3 model files are incomplete")
        finally:
            asr._state["downloading"] = False

def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        import sherpa_onnx
        ensure_model()
        _recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(MODEL_DIR / FILES[0]), decoder=str(MODEL_DIR / FILES[1]),
            joiner=str(MODEL_DIR / FILES[2]), tokens=str(MODEL_DIR / FILES[3]),
            num_threads=cpu_infer_threads(cap=4, floor=2), sample_rate=16000,
            feature_dim=80, decoding_method="greedy_search", model_type="nemo_transducer",
            provider="cpu")
    return _recognizer

def _transcribe_local(wav_bytes):
    samples, rate = asr.wav_bytes_to_float(wav_bytes)
    samples = asr._resample(samples, rate, 16000)
    rec = _get_recognizer()
    stream = rec.create_stream()
    stream.accept_waveform(16000, samples)
    rec.decode_stream(stream)
    return (stream.result.text or "").strip()
