"""Optional local TeraTTSv2. Models live in application data, not the B pack."""
from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from ..paths import DATA_DIR

MODEL_DIR = DATA_DIR / "optional-models" / "teratts-v2"
GPU_RUNTIME_DIR = DATA_DIR / "optional-runtime" / "ort-gpu"
MODEL_URL = "https://huggingface.co/TeraSpace/TeraTTSv2"
MODEL_SOURCES = (("ModelScope", "https://modelscope.cn"),
                 ("Hugging Face", "https://huggingface.co"),
                 ("Hugging Face mirror", "https://hf-mirror.com"))
REVISION = "75983ac"
SAMPLE_RATE = 44100
VOICES = [
    {"id": "ru_f1", "label": "Tera · ru_f1", "engine": "tera", "lang": "ru"},
    {"id": "ru_f2", "label": "Tera · ru_f2", "engine": "tera", "lang": "ru"},
    {"id": "ru_m1", "label": "Tera · ru_m1", "engine": "tera", "lang": "ru"},
    {"id": "ru_m5", "label": "Tera · ru_m5", "engine": "tera", "lang": "ru"},
    {"id": "eng_f3", "label": "Tera · eng_f3", "engine": "tera", "lang": "en"},
    {"id": "eng_f4_whisper", "label": "Tera · eng_f4_whisper", "engine": "tera", "lang": "en"},
    {"id": "eng_f5", "label": "Tera · eng_f5", "engine": "tera", "lang": "en"},
    {"id": "eng_m2_whisper", "label": "Tera · eng_m2_whisper", "engine": "tera", "lang": "en"},
    {"id": "eng_m3", "label": "Tera · eng_m3", "engine": "tera", "lang": "en"},
    {"id": "eng_m4", "label": "Tera · eng_m4", "engine": "tera", "lang": "en"},
]
_state = {"downloading": False, "loading": False, "gpu_downloading": False, "message": "", "source": ""}
_guard = threading.Lock()
_download_guard = threading.Lock()
_model = None
_runtime = None
_provider = "CPUExecutionProvider"
_gpu_proc = None
_gpu_messages = None


def installed() -> bool:
    paths = ["teratts.py", "teratts_ruaccent.py", "unicode_indexer.json", "models/text_encoder.onnx",
             "models/duration_predictor.onnx", "models/sampler_distilled_cfg3_8step.onnx", "models/vocoder.onnx",
             "ruaccent/dictionary/accents.json.gz", "ruaccent/dictionary/omographs.json.gz",
             "ruaccent/dictionary/yo_words.json.gz", "ruaccent/dictionary/yo_homographs.json.gz"]
    for voice in VOICES:
        paths.extend(f"styles/{voice['id']}/{name}" for name in ("style_ttl.npy", "style_dp.npy"))
    for name in ("nn_accent", "nn_omograph/turbo3.1", "nn_stress_usage_predictor", "nn_yo_homograph_resolver"):
        paths.extend(f"ruaccent/nn/{name}/{file}" for file in ("model.onnx", "config.json", "tokenizer_config.json"))
    return all((MODEL_DIR / path).is_file() and (MODEL_DIR / path).stat().st_size > 0 for path in paths)


def status() -> dict:
    return {"engine": "tera", "installed": installed(), "ready": bool(_gpu_proc and _gpu_proc.poll() is None),
            "downloading": _state["downloading"], "loading": _state["loading"],
            "message": _state["message"], "url": MODEL_URL,
            "gpu_runtime": (GPU_RUNTIME_DIR / "onnxruntime").is_dir(),
            "gpu_downloading": _state["gpu_downloading"],
            "source": _state["source"],
            "provider": "CUDA" if _gpu_proc and _gpu_proc.poll() is None else ""}


def _probe_source(source):
    name, endpoint = source
    url = (f"{endpoint}/openapi/v1/models?search=TeraTTSv2&page_size=50"
           if name == "ModelScope" else
           f"{endpoint}/api/models/TeraSpace/TeraTTSv2/revision/{REVISION}")
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "xiaoke-ai/0.1"})
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status != 200:
                raise OSError(f"HTTP {response.status}")
            metadata = json.load(response)
            if name == "ModelScope":
                models = (metadata.get("data") or {}).get("models") or []
                if not any(str(model.get("id") or "").lower() == "teraspace/terattsv2" for model in models):
                    raise ValueError("official model is not available on ModelScope")
            elif not str(metadata.get("sha") or "").startswith(REVISION):
                raise ValueError("model revision does not match")
        return time.monotonic() - start
    except Exception:
        return float("inf")


def _rank_sources():
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(MODEL_SOURCES)) as pool:
        delays = list(pool.map(_probe_source, MODEL_SOURCES))
    return [source for delay, source in sorted(zip(delays, MODEL_SOURCES), key=lambda pair: pair[0])
            if delay != float("inf") or source[0] != "ModelScope"]


class SnapshotVerificationError(RuntimeError):
    def __init__(self, relative: str, reason: str):
        super().__init__(f"TeraTTS file {reason}: {relative}")
        self.relative = relative


def _verify_snapshot(directory: Path):
    manifest = json.loads((Path(__file__).with_name("teratts_manifest.json")).read_text(encoding="utf-8"))
    for relative, expected in manifest.items():
        path = directory / relative
        if not path.is_file() or path.stat().st_size != expected["size"]:
            raise SnapshotVerificationError(relative, "missing or wrong size")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected["sha256"]:
            raise SnapshotVerificationError(relative, "checksum mismatch")
    return manifest


def download() -> None:
    try:
        from huggingface_hub import snapshot_download
        _state["message"] = "Checking download sources…"
        staging = MODEL_DIR.parent / (MODEL_DIR.name + "-download")
        errors = []
        for name, endpoint in _rank_sources():
            _state.update(source=name, message=f"Downloading TeraTTSv2 from {name}…")
            try:
                if name == "ModelScope":
                    from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot
                    ms_snapshot("TeraSpace/TeraTTSv2", local_dir=str(staging),
                                ignore_patterns=["__pycache__/*"])
                else:
                    snapshot_download("TeraSpace/TeraTTSv2", revision=REVISION, local_dir=str(staging),
                                      endpoint=endpoint, ignore_patterns=["__pycache__/*"])
                _state["message"] = f"Verifying TeraTTSv2 from {name}…"
                manifest = _verify_snapshot(staging)
                with _guard:
                    _stop_gpu_worker()
                    for relative in manifest:
                        source, dest = staging / relative, MODEL_DIR / relative
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(source, dest)
                if not installed():
                    raise RuntimeError("TeraTTSv2 download is incomplete")
                _state["message"] = f"TeraTTSv2 downloaded from {name}"
                break
            except Exception as exc:
                if isinstance(exc, SnapshotVerificationError):
                    (staging / exc.relative).unlink(missing_ok=True)
                errors.append(f"{name}: {exc}")
        else:
            raise RuntimeError("; ".join(errors))
    except Exception as exc:
        _state["message"] = str(exc)
    finally:
        _state["downloading"] = False


def start_download() -> bool:
    with _download_guard:
        if _state["downloading"]:
            return False
        _state.update(downloading=True, message="Downloading TeraTTSv2…")
        threading.Thread(target=download, daemon=True).start()
        return True


def start_gpu_download() -> bool:
    with _download_guard:
        if _state["gpu_downloading"]:
            return False
        _state.update(gpu_downloading=True, message="Installing NVIDIA GPU runtime…")
    def install():
        try:
            GPU_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            result = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--upgrade",
                                     "--target", str(GPU_RUNTIME_DIR), "onnxruntime-gpu==1.23.2"],
                                    capture_output=True, text=True, timeout=1200,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout)[-1000:])
            if not (GPU_RUNTIME_DIR / "onnxruntime").is_dir():
                raise RuntimeError("GPU runtime install incomplete")
            _state["message"] = "NVIDIA GPU runtime installed"
        except Exception as exc:
            _state["message"] = str(exc)
        finally:
            _state["gpu_downloading"] = False
    threading.Thread(target=install, daemon=True).start()
    return True


def release() -> None:
    global _model, _runtime
    with _guard:
        _stop_gpu_worker()
        if _runtime is not None:
            _runtime.clear_session_cache()
        _model = None
        _runtime = None


def _load():
    global _model, _runtime
    if _model is not None:
        return _model
    if not installed():
        raise FileNotFoundError("TeraTTSv2 model missing: download it in voice settings")
    _state.update(loading=True, message="Loading TeraTTSv2…")
    try:
        # Load the pinned release locally, without Transformers remote-code loading.
        sys.path.insert(0, str(MODEL_DIR))
        spec = importlib.util.spec_from_file_location("companion_teratts_runtime", MODEL_DIR / "teratts.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load TeraTTS runtime")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _runtime = module
        _model = module.load_model(MODEL_DIR, model="distilled", provider=_provider, threads=4)
        _state["message"] = "TeraTTSv2 ready"
        return _model
    except Exception as exc:
        _state["message"] = str(exc)
        raise
    finally:
        _state["loading"] = False


def _stop_gpu_worker() -> None:
    global _gpu_proc, _gpu_messages
    proc, _gpu_proc = _gpu_proc, None
    _gpu_messages = None
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def _ensure_gpu_worker():
    global _gpu_proc, _gpu_messages
    if _gpu_proc and _gpu_proc.poll() is None:
        return
    if not installed():
        raise FileNotFoundError("TeraTTSv2 model missing: download it in voice settings")
    if not (GPU_RUNTIME_DIR / "onnxruntime").is_dir():
        raise RuntimeError("TeraTTS GPU runtime missing: install the CUDA runtime in voice settings")
    env = os.environ.copy()
    env["COMPANION_TERA_GPU_RUNTIME"] = str(GPU_RUNTIME_DIR)
    root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    _gpu_messages = queue.Queue()
    _gpu_proc = subprocess.Popen([sys.executable, "-u", "-m", "app.services.tts_tera_worker"],
        cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        encoding="utf-8", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    proc, messages = _gpu_proc, _gpu_messages
    def read_messages():
        for line in proc.stdout:
            try:
                messages.put(json.loads(line))
            except json.JSONDecodeError:
                messages.put({"kind": "error", "message": "Unexpected TeraTTS worker response"})
        messages.put({"kind": "closed"})
    threading.Thread(target=read_messages, daemon=True).start()
    _state.update(loading=True, message="Loading TeraTTSv2 on NVIDIA GPU…")
    try:
        msg = messages.get(timeout=120)
        if msg.get("kind") != "ready":
            raise RuntimeError(msg.get("message") or "TeraTTS GPU worker failed to start")
        _state["message"] = "TeraTTSv2 ready (NVIDIA GPU)"
    except Exception:
        _stop_gpu_worker()
        raise
    finally:
        _state["loading"] = False


def start_warmup() -> bool:
    if _state["loading"] or (_gpu_proc and _gpu_proc.poll() is None):
        return False
    _state.update(loading=True, message="Preparing TeraTTSv2 on NVIDIA GPU…")
    def run():
        try:
            with _guard:
                _ensure_gpu_worker()
        except Exception as exc:
            _state["message"] = str(exc)
        finally:
            _state["loading"] = False
    threading.Thread(target=run, daemon=True).start()
    return True


def _produce(text: str, voice: str, cancelled: threading.Event, out: queue.Queue, language: str = "ru") -> None:
    try:
        with _guard:
            if cancelled.is_set():
                return
            _ensure_gpu_worker()
            if cancelled.is_set():
                return
            _gpu_proc.stdin.write(json.dumps({"text": text, "voice": voice, "language": language}) + "\n")
            _gpu_proc.stdin.flush()
            while True:
                if cancelled.is_set():
                    _stop_gpu_worker()
                    break
                try:
                    msg = _gpu_messages.get(timeout=0.1)
                except queue.Empty:
                    continue
                kind = msg.get("kind")
                if kind == "audio":
                    out.put(("audio", base64.b64decode(msg["data"])))
                elif kind == "end":
                    break
                else:
                    message = msg.get("message") or "TeraTTS GPU worker stopped"
                    _stop_gpu_worker()
                    raise RuntimeError(message)
    except Exception as exc:
        _state["message"] = str(exc)
        out.put(("error", str(exc)))
    finally:
        out.put(("end", None))


async def synthesize_pcm(text: str, voice: str, cancelled: threading.Event, language: str = "ru"):
    if voice not in {v["id"] for v in VOICES}:
        raise ValueError("Unknown TeraTTS voice")
    out = queue.Queue()
    threading.Thread(target=_produce, args=(text, voice, cancelled, out, language), daemon=True).start()
    while True:
        kind, payload = await asyncio.to_thread(out.get)
        if kind == "end":
            break
        if kind == "error":
            raise RuntimeError(payload)
        yield payload
