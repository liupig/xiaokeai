"""记忆向量：显式选本地 MiniLM / 字节豆包 / 千问，不再静默探测网关。"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .embed_local import probe as probe_local_minilm

PROVIDERS = ("auto", "local", "doubao", "qwen")
DOUBAO_BASE = "https://ark.cn-beijing.volces.com/api/v3"
QWEN_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_NATIVE = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"

DOUBAO_MODELS = (
    "doubao-embedding-large",
    "doubao-embedding",
    "doubao-embedding-large-text-240915",
    "doubao-embedding-text-240515",
)
QWEN_MODELS = (
    "text-embedding-v3",
    "text-embedding-v4",
    "text-embedding-v2",
)

_VOLC_HINT = ("ark.cn-beijing.volces.com", "volces.com", "volcengine")
_QWEN_HINT = ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com")


def normalize_provider(raw: Any) -> str:
    val = str(raw or "auto").strip().lower()
    return val if val in PROVIDERS else "auto"


def collection_name(sig: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", sig).strip("_")
    return f"companion_{safe}"[:120]


def embed_sig(embedder: Any) -> str:
    provider = getattr(embedder, "provider", "") or "none"
    model = (
        getattr(embedder, "model_name", None)
        or getattr(embedder, "model", None)
        or "none"
    )
    dims = int(getattr(embedder, "dims", 0) or 0)
    return f"{provider}:{model}:{dims}"


def guess_provider(llm_conf: Dict[str, Any]) -> str:
    base = (llm_conf.get("base_url") or "").strip().lower()
    if any(h in base for h in _VOLC_HINT):
        return "doubao"
    if any(h in base for h in _QWEN_HINT):
        return "qwen"
    return "local"


def _env_key(*names: str) -> str:
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


def doubao_credentials(llm_conf: Dict[str, Any]) -> Tuple[str, str]:
    key = (llm_conf.get("api_key") or "").strip()
    base = (llm_conf.get("base_url") or "").rstrip("/")
    if key and any(h in base.lower() for h in _VOLC_HINT):
        return key, DOUBAO_BASE
    env_key = _env_key("ARK_API_KEY", "VOLC_ARK_API_KEY")
    if env_key:
        return env_key, DOUBAO_BASE
    return "", ""


def qwen_credentials(llm_conf: Dict[str, Any]) -> Tuple[str, str]:
    key = (llm_conf.get("api_key") or "").strip()
    base = (llm_conf.get("base_url") or "").rstrip("/")
    if key and any(h in base.lower() for h in _QWEN_HINT):
        return key, QWEN_BASE
    env_key = _env_key("DASHSCOPE_API_KEY")
    if env_key:
        return env_key, QWEN_BASE
    return "", ""


class RemoteEmbedder:
    """OpenAI 兼容 /embeddings。字节走方舟，千问走百炼兼容模式。"""

    def __init__(self, api_key: str, base_url: str, model: str, dims: int, *,
                 provider: str, native: bool = False, input_list: bool = True,
                 dimensions: Optional[int] = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_name = model
        self.provider = provider
        self.dims = dims
        self._native = native
        self._input_list = input_list
        self._dimensions = dimensions
        self.config = type("Cfg", (), {"embedding_dims": dims, "model": model})()

    @classmethod
    def connect(cls, provider: str, api_key: str, base_url: str,
                models: Tuple[str, ...]) -> Optional["RemoteEmbedder"]:
        if not api_key or not base_url:
            return None
        last = ""
        with httpx.Client(timeout=httpx.Timeout(12, connect=6), trust_env=False) as client:
            for model in models:
                for payload in (
                    {"model": model, "input": ["记忆召回探测"], "encoding_format": "float"},
                    {"model": model, "input": "记忆召回探测"},
                    {"model": model, "input": ["记忆召回探测"]},
                ):
                    try:
                        resp = client.post(
                            f"{base_url.rstrip('/')}/embeddings",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json=payload,
                        )
                    except httpx.HTTPError as exc:
                        last = str(exc)
                        continue
                    if resp.status_code != 200:
                        last = f"{model} HTTP {resp.status_code}"
                        continue
                    try:
                        vec = resp.json()["data"][0]["embedding"]
                    except (KeyError, IndexError, TypeError, ValueError) as exc:
                        last = f"{model} parse {exc}"
                        continue
                    if isinstance(vec, list) and len(vec) >= 32:
                        print(f"[memory] embedder {provider} {model} dim={len(vec)}")
                        return cls(
                            api_key, base_url, model, len(vec),
                            provider=provider,
                            input_list=isinstance(payload.get("input"), list),
                            dimensions=1024 if provider == "qwen" and len(vec) == 1024 else None,
                        )
        if provider == "qwen":
            found = cls._dashscope_native(api_key)
            if found is not None:
                return found
        print(f"[memory] {provider} embeddings failed: {last}")
        return None

    @classmethod
    def _dashscope_native(cls, api_key: str) -> Optional["RemoteEmbedder"]:
        with httpx.Client(timeout=httpx.Timeout(12, connect=6), trust_env=False) as client:
            for model in QWEN_MODELS:
                try:
                    resp = client.post(
                        QWEN_NATIVE,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": model, "input": {"texts": ["记忆召回探测"]},
                              "parameters": {"text_type": "query"}},
                    )
                except httpx.HTTPError:
                    continue
                if resp.status_code != 200:
                    continue
                try:
                    vec = resp.json()["output"]["embeddings"][0]["embedding"]
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
                if isinstance(vec, list) and len(vec) >= 32:
                    print(f"[memory] embedder qwen native {model} dim={len(vec)}")
                    return cls(api_key, QWEN_NATIVE, model, len(vec),
                               provider="qwen", native=True)
        return None

    def _post(self, texts: List[str]) -> List[List[float]]:
        blob = [(t or "").strip() or " " for t in texts]
        with httpx.Client(timeout=httpx.Timeout(30, connect=8), trust_env=False) as client:
            if self._native:
                resp = client.post(
                    self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={"model": self.model, "input": {"texts": blob},
                          "parameters": {"text_type": "query"}},
                )
                resp.raise_for_status()
                rows = resp.json()["output"]["embeddings"]
                rows = sorted(rows, key=lambda x: x.get("text_index", 0))
                return [row["embedding"] for row in rows]
            payload: Dict[str, Any] = {
                "model": self.model,
                "input": blob if self._input_list or len(blob) > 1 else blob[0],
            }
            if self._dimensions:
                payload["dimensions"] = self._dimensions
            resp = client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda x: x.get("index", 0))
        out = [row["embedding"] for row in data]
        if len(out) != len(blob):
            raise RuntimeError("embed batch size mismatch")
        return out

    def embed(self, text, memory_action=None):
        return self._post([(text or "").strip() or " "])[0]

    def embed_batch(self, texts, memory_action="add"):
        blob = [(t or "").strip() or " " for t in texts]
        return self._post(blob) if blob else []


def _tag_local(emb: Any) -> Any:
    if emb is None:
        return None
    if not getattr(emb, "provider", None):
        emb.provider = "local"
    if not getattr(emb, "model_name", None):
        emb.model_name = "minilm"
    return emb


def resolve(llm_conf: Dict[str, Any], choice: str) -> Tuple[Optional[Any], str]:
    """返回 (embedder, note)。在线失败时回退本地 MiniLM，再没有则 None。"""
    want = normalize_provider(choice)
    if want == "auto":
        want = guess_provider(llm_conf)

    note = ""
    emb = None
    if want == "doubao":
        key, base = doubao_credentials(llm_conf)
        emb = RemoteEmbedder.connect("doubao", key, base, DOUBAO_MODELS)
        if emb is None:
            note = "豆包 embedding 不可用（需要火山方舟 API Key），改用本地 MiniLM"
    elif want == "qwen":
        key, base = qwen_credentials(llm_conf)
        emb = RemoteEmbedder.connect("qwen", key, base, QWEN_MODELS)
        if emb is None:
            note = "千问 embedding 不可用（需要百炼 sk- Key），改用本地 MiniLM"
    elif want == "local":
        emb = _tag_local(probe_local_minilm())
        if emb is None:
            note = "本地 MiniLM 未就绪"
        return emb, note

    if emb is not None:
        return emb, ""
    fallback = _tag_local(probe_local_minilm())
    if fallback is None:
        return None, note or "没有可用的 embedding"
    return fallback, note
