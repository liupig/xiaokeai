"""本地推理框架选型。

不能装 vLLM-Omni：官方 Qwen3-TTS 加速框架要求 transformers>=5.5，
会把现有 qwen-tts（钉死 4.57.3）升坏。三块各自用能共处的框架：

  ASR        ONNX Runtime      经 sherpa-onnx 跑 SenseVoice INT8
  TTS        CUDA Graph        fast_tts 捕获 Talker/Predictor（流式）
             TorchInductor     无 GPU 时 torch.compile
  Embedding  fastembed         ONNX Runtime 上的向量推理框架（量化 MiniLM）
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
            "note": "Qwen 官方 vLLM-Omni 与当前 qwen-tts 的 transformers 4.57 不兼容；流式走 CUDA Graph。",
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
