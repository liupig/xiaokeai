"""下载 MiniCPM-V 4.7 1B 到上一级 models/（优先 ModelScope）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT.parent / "models" / "MiniCPM-V-4.7-1B"
MS_ID = "OpenBMB/MiniCPM-V-4.7-1B"
HF_ID = "openbmb/MiniCPM-V-4.7-1B"


def ready(dest: Path) -> bool:
    if not (dest / "config.json").is_file():
        return False
    return any(dest.glob("*.safetensors")) or any(dest.glob("*.bin"))


def _ms() -> bool:
    DEST.mkdir(parents=True, exist_ok=True)
    try:
        from modelscope.hub.snapshot_download import snapshot_download
        snapshot_download(model_id=MS_ID, local_dir=str(DEST))
        return ready(DEST)
    except Exception as exc:
        print(f"[ms] {MS_ID} 失败：{exc}")
        return False


def _hf() -> bool:
    DEST.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=HF_ID, local_dir=str(DEST))
        return ready(DEST)
    except Exception as exc:
        print(f"[hf] {HF_ID} 失败：{exc}")
        return False


def main() -> int:
    if ready(DEST):
        print(f"权重已在 {DEST}")
        return 0
    print(f"下载 MiniCPM-V-4.7-1B 到 {DEST}")
    ok = _ms() or _hf()
    print("完成" if ok else "下载失败，见上方日志")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
