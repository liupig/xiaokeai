"""三个推理 worker 的运行时策略：线程隔离、GPU 让渡、CUDA 分配。

必须在 import torch / sherpa_onnx 之前调用 prepare_worker。
ASR / Memory 不碰 GPU；TTS 独占 CUDA，CPU 线程压到最低以免和识别抢核。
"""
from __future__ import annotations

import os
from typing import Any, Tuple

_TTS_TORCH_READY = False


def cpu_count() -> int:
    return os.cpu_count() or 4


def cpu_infer_threads(*, cap: int = 4, floor: int = 2) -> int:
    """单会话推理线程。超过 4 往往被内存带宽卡住，还会和别的 worker 抢核。"""
    n = cpu_count()
    return max(floor, min(cap, max(1, n // 2)))


def pin_cpu_threads(n: int, torch_mod: Any = None) -> None:
    n = max(1, int(n))
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "ORT_NUM_THREADS",
    ):
        os.environ[key] = str(n)
    if torch_mod is not None:
        try:
            torch_mod.set_num_threads(n)
            torch_mod.set_num_interop_threads(1)
        except Exception:
            pass


def hide_gpu() -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["HIP_VISIBLE_DEVICES"] = ""


def _cuda_alloc_conf() -> str:
    # Windows 上 expandable_segments 不稳定；只限制块大小减轻碎片 OOM。
    if os.name == "nt":
        return "max_split_size_mb:128"
    return "expandable_segments:True,max_split_size_mb:128"


def prepare_worker(role: str) -> int:
    """返回建议的 CPU 推理线程数。"""
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ["MEM0_TELEMETRY"] = "False"
    if role == "asr":
        hide_gpu()
        n = cpu_infer_threads(cap=4, floor=2)
        pin_cpu_threads(n)
        return n
    if role == "memory":
        hide_gpu()
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        n = cpu_infer_threads(cap=2, floor=1)
        pin_cpu_threads(n)
        return n
    if role == "tts":
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", _cuda_alloc_conf())
        return 1
    return 1


def configure_torch_for_tts() -> Tuple[str, Any]:
    """加载 Qwen TTS 前调用。GPU 用 bf16（Turing 等不支持则 fp16），CPU 用 fp32。"""
    global _TTS_TORCH_READY
    import torch

    gpu = bool(torch.cuda.is_available())
    if gpu:
        pin_cpu_threads(1, torch)
        if not _TTS_TORCH_READY:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            try:
                torch.set_float32_matmul_precision("high")
            except Exception:
                pass
            for name in ("enable_flash_sdp", "enable_mem_efficient_sdp", "enable_math_sdp"):
                fn = getattr(torch.backends.cuda, name, None)
                if callable(fn):
                    try:
                        fn(True)
                    except Exception:
                        pass
        bf16 = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
        dtype = torch.bfloat16 if bf16 else torch.float16
        device = "cuda:0"
    else:
        pin_cpu_threads(cpu_infer_threads(cap=6, floor=2), torch)
        dtype = torch.float32
        device = "cpu"
    _TTS_TORCH_READY = True
    return device, dtype
