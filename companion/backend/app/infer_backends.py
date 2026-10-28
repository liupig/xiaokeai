"""本地推理框架选型。

语音用 dayn9t 的 qwen-tts 分支，和眼睛一样钉在 transformers 5.20.2。
三块各自用能共处的框架：

  ASR        ONNX Runtime      经 sherpa-onnx 跑 SenseVoice INT8
  TTS        CUDA Graph        fast_tts 捕获 Talker/Predictor（流式）
             TorchInductor     无 GPU 时 torch.compile
  Embedding  fastembed         ONNX Runtime 上的向量推理框架（量化 MiniLM）

MiniCPM-o 4.5 Omni 不进本进程：官方 PyTorch 要 transformers==4.51.0，
会把现在的 5.20.2 降坏。Omni 走云端 Chat Completions / Realtime，
或把 realtime_host 指到自建 Gateway。
"""
from __future__ import annotations

import os
from typing import Any, Dict


def asr_framework() -> Dict[str, Any]:
    return {
        "name": "onnxruntime",
        "via": "sherpa-onnx",
        "provider": os.environ.get("COMPANION_ASR_PROVIDER") or "cpu",
    }


def tts_framework(device: str) -> Dict[str, Any]:
    if str(device).startswith("cuda"):
        return {
            "name": "cuda_graph",
            "via": "fast_tts",
            "note": "流式走 CUDA Graph。",
        }
    return {
        "name": "torch.inductor",
        "via": "torch.compile",
        "note": "CPU 路径用 TorchInductor；GPU 仍走 CUDA Graph。",
    }


def embed_framework() -> Dict[str, Any]:
    try:
        import fastembed  # noqa: F401
        return {"name": "fastembed", "via": "onnxruntime"}
    except Exception:
        return {"name": "pytorch", "via": "transformers"}
