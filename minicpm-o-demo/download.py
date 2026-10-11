"""下载 MiniCPM-o 4.5 权重（优先 ModelScope）。"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
ASSETS = ROOT / "assets"
PT_DIR = MODELS / "MiniCPM-o-4_5"
GGUF_DIR = MODELS / "MiniCPM-o-4_5-gguf"
AWQ_DIR = MODELS / "MiniCPM-o-4_5-AWQ"

REF_URLS = [
    "https://huggingface.co/datasets/openbmb/MiniCPM-o-demo/resolve/main/HT_ref_audio.wav",
    "https://hf-mirror.com/datasets/openbmb/MiniCPM-o-demo/resolve/main/HT_ref_audio.wav",
]

GGUF_MS = "OpenBMB/MiniCPM-o-4_5-gguf"
PT_MS = "OpenBMB/MiniCPM-o-4_5"
AWQ_MS = "OpenBMB/MiniCPM-o-4_5-AWQ"
GGUF_HF = "openbmb/MiniCPM-o-4_5-gguf"
PT_HF = "openbmb/MiniCPM-o-4_5"
AWQ_HF = "openbmb/MiniCPM-o-4_5-AWQ"

GGUF_ALLOW = [
    "MiniCPM-o-4_5-Q4_K_M.gguf",
    "audio/MiniCPM-o-4_5-audio-F16.gguf",
    "tts/MiniCPM-o-4_5-tts-F16.gguf",
    "tts/MiniCPM-o-4_5-projector-F16.gguf",
    "vision/MiniCPM-o-4_5-vision-F16.gguf",
    "token2wav-gguf/encoder.gguf",
    "token2wav-gguf/flow_matching.gguf",
    "token2wav-gguf/flow_extra.gguf",
    "token2wav-gguf/hifigan2.gguf",
    "token2wav-gguf/prompt_cache.gguf",
]


def _ms(repo: str, dest: Path, allow=None) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        from modelscope.hub.snapshot_download import snapshot_download
        kwargs = {"model_id": repo, "local_dir": str(dest)}
        if allow:
            kwargs["allow_patterns"] = allow
        snapshot_download(**kwargs)
        return True
    except Exception as exc:
        print(f"[ms] {repo} 失败：{exc}")
        return False


def _hf(repo: str, dest: Path, allow=None) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from huggingface_hub import snapshot_download
        kwargs = {"repo_id": repo, "local_dir": str(dest)}
        if allow:
            kwargs["allow_patterns"] = allow
        snapshot_download(**kwargs)
        return True
    except Exception as exc:
        print(f"[hf] {repo} 失败：{exc}")
        return False


def download_ref() -> Path:
    ASSETS.mkdir(parents=True, exist_ok=True)
    dest = ASSETS / "ref.wav"
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    for url in REF_URLS:
        try:
            print(f"下载参考音色 {url}")
            urllib.request.urlretrieve(url, dest)
            if dest.stat().st_size > 1000:
                return dest
        except Exception as exc:
            print(f"  失败：{exc}")
    print("没有拉到官方参考音频，首轮会用静音占位（声音会比较怪）")
    return dest


def download_gguf() -> bool:
    print("下载 GGUF Q4 全套（LLM Q4_K_M + 视觉/听觉/TTS/Token2Wav）约 8GB…")
    if _ms(GGUF_MS, GGUF_DIR, GGUF_ALLOW):
        return True
    return _hf(GGUF_HF, GGUF_DIR, GGUF_ALLOW)


def download_awq() -> bool:
    print("下载 AWQ int4 权重（PyTorch 路径，约 11GB 显存）…")
    if _ms(AWQ_MS, AWQ_DIR):
        return True
    return _hf(AWQ_HF, AWQ_DIR)


def download_pt() -> bool:
    print("下载完整 PyTorch 权重（更大）…")
    if _ms(PT_MS, PT_DIR):
        return True
    return _hf(PT_HF, PT_DIR)


def main() -> int:
    what = (sys.argv[1] if len(sys.argv) > 1 else "gguf").lower()
    download_ref()
    jobs = {
        "gguf": [download_gguf],
        "awq": [download_awq],
        "pt": [download_pt],
        "all": [download_gguf, download_awq],
    }.get(what)
    if not jobs:
        print("用法: python download.py [gguf|awq|pt|all]")
        return 2
    ok = True
    for fn in jobs:
        ok = fn() and ok
    print("完成" if ok else "有步骤失败，见上方日志")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
