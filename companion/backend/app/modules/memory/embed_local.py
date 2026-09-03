"""本地 embedding：优先用项目里的 data/embed/minilm（PyTorch INT8），
fastembed ONNX 仅在 data/embed/fastembed 已有缓存时使用，运行时不联网下载。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, List, Optional

from ...infer_runtime import cpu_infer_threads
from ...paths import FASTEMBED_DIR, MINILM_DIR

_LOCAL_MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_LOCAL_MINILM_DIMS = 384
_probe: dict[str, Any] = {"tried": False, "emb": None}


def probe() -> Optional[Any]:
    if _probe["tried"]:
        return _probe["emb"]
    # 优先用项目里的 fastembed ONNX；没有则用 data/embed/minilm（PyTorch）。都不联网。
    emb = FastEmbedEmbedder.probe()
    if emb is None:
        emb = TorchMiniLMEmbedder.probe()
    _probe["emb"] = emb
    _probe["tried"] = True
    return emb


def _torch_weight_dir() -> Optional[Path]:
    bundled = MINILM_DIR
    if _has_torch_weights(bundled):
        return bundled
    hub = Path.home() / ".cache" / "huggingface" / "hub" / (
        "models--" + _LOCAL_MINILM.replace("/", "--")
    )
    candidates: List[Path] = []
    ref = hub / "refs" / "main"
    if ref.is_file():
        rev = ref.read_text(encoding="utf-8").strip()
        if rev:
            candidates.append(hub / "snapshots" / rev)
    snaps = hub / "snapshots"
    if snaps.is_dir():
        candidates.extend(sorted(snaps.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True))
    seen: set[str] = set()
    for snap in candidates:
        key = str(snap)
        if key in seen or not snap.is_dir():
            continue
        seen.add(key)
        if _has_torch_weights(snap):
            return snap
    return None


def _has_torch_weights(folder: Path) -> bool:
    has_w = (folder / "model.safetensors").is_file() or (folder / "pytorch_model.bin").is_file()
    return has_w and (folder / "config.json").is_file()


_FASTEMBED_MODEL_DIR = FASTEMBED_DIR / "qdrant-minilm-onnx"


def _fastembed_cache_ok() -> bool:
    return (_FASTEMBED_MODEL_DIR / "model_optimized.onnx").is_file()


class FastEmbedEmbedder:
    """Qdrant fastembed：ONNX Runtime。权重在 data/embed/fastembed/qdrant-minilm-onnx。"""

    def __init__(self, model):
        self.model = model
        self.dims = _LOCAL_MINILM_DIMS
        self.model_name = "minilm"
        self.config = type("Cfg", (), {"embedding_dims": self.dims, "model": "minilm"})()
        self._gate = threading.Lock()

    @classmethod
    def probe(cls) -> Optional["FastEmbedEmbedder"]:
        if not _fastembed_cache_ok():
            print("[memory] fastembed ONNX missing (data/embed/fastembed/qdrant-minilm-onnx)")
            return None
        try:
            from fastembed import TextEmbedding
        except Exception as exc:
            print(f"[memory] fastembed unavailable: {exc}")
            return None
        kwargs: dict[str, Any] = {
            "model_name": _LOCAL_MINILM,
            "cache_dir": str(FASTEMBED_DIR),
            "specific_model_path": str(_FASTEMBED_MODEL_DIR),
            "threads": cpu_infer_threads(cap=2, floor=1),
            "providers": ["CPUExecutionProvider"],
            "cuda": False,
            "local_files_only": True,
        }
        try:
            model = TextEmbedding(**kwargs)
            vec = next(model.embed(["ping"]))
            if len(vec) != _LOCAL_MINILM_DIMS:
                print(f"[memory] fastembed unexpected dim={len(vec)}")
                return None
            print("[memory] local MiniLM ready dim=384 (fastembed / onnxruntime)")
            return cls(model)
        except TypeError:
            kwargs.pop("local_files_only", None)
            try:
                os.environ["HF_HUB_OFFLINE"] = "1"
                model = TextEmbedding(**kwargs)
                vec = next(model.embed(["ping"]))
                if len(vec) != _LOCAL_MINILM_DIMS:
                    return None
                print("[memory] local MiniLM ready dim=384 (fastembed / onnxruntime)")
                return cls(model)
            except Exception as exc:
                print(f"[memory] fastembed load fail: {exc}")
                return None
        except Exception as exc:
            print(f"[memory] fastembed load fail: {exc}")
            return None

    def embed(self, text, memory_action=None):
        return self.embed_batch([text or " "])[0]

    def embed_batch(self, texts, memory_action="add"):
        blob = [(t or "").strip() or " " for t in texts]
        with self._gate:
            return [v.tolist() for v in self.model.embed(blob)]


class TorchMiniLMEmbedder:
    """fastembed 不可用时的兜底。动态量化 Linear → INT8，强制 CPU。"""

    def __init__(self, model, tokenizer, torch_mod):
        self.model = model
        self.tok = tokenizer
        self.torch = torch_mod
        self.dims = _LOCAL_MINILM_DIMS
        self.model_name = "minilm"
        self.config = type("Cfg", (), {"embedding_dims": self.dims, "model": "minilm"})()
        self._gate = threading.Lock()

    @classmethod
    def probe(cls) -> Optional["TorchMiniLMEmbedder"]:
        local = _torch_weight_dir()
        if not local:
            print("[memory] MiniLM weights missing (data/embed/minilm)")
            return None
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:
            print(f"[memory] MiniLM import fail: {exc}")
            return None
        prev = {k: os.environ.get(k) for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            tok = AutoTokenizer.from_pretrained(str(local), local_files_only=True)
            model = AutoModel.from_pretrained(
                str(local), local_files_only=True, low_cpu_mem_usage=False,
            )
            model.eval()
            for p in model.parameters():
                p.requires_grad_(False)
            if next(model.parameters()).device.type != "cpu":
                model.to("cpu")
            try:
                model = torch.quantization.quantize_dynamic(
                    model, {torch.nn.Linear}, dtype=torch.qint8,
                )
                quant = "int8"
            except Exception as exc:
                print(f"[memory] MiniLM torch INT8 skip: {exc}")
                quant = "fp32"
            torch.set_num_threads(cpu_infer_threads(cap=2, floor=1))
            dummy = tok("ping", return_tensors="pt")
            with torch.inference_mode():
                hid = model(**dummy).last_hidden_state
            if hid.shape[-1] != _LOCAL_MINILM_DIMS:
                print(f"[memory] MiniLM unexpected dim={hid.shape[-1]}")
            print(f"[memory] local MiniLM ready dim=384 (torch {quant} cpu)")
            return cls(model, tok, torch)
        except Exception as exc:
            print(f"[memory] MiniLM load fail: {exc}")
            return None
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def embed(self, text, memory_action=None):
        return self.embed_batch([text or " "])[0]

    def embed_batch(self, texts, memory_action="add"):
        blob = [(t or "").strip() or " " for t in texts]
        with self._gate:
            enc = self.tok(
                blob, padding=True, truncation=True, max_length=256, return_tensors="pt",
            )
            with self.torch.inference_mode():
                hidden = self.model(**enc).last_hidden_state
                mask = enc["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
                pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                pooled = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
            return pooled.cpu().tolist()
