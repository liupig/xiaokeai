"""记忆：LLM 抽长期事实，网关向量召回后注入 prompt。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx
from sqlmodel import Session, select

from ...models import Character, MemoryFact
from ...paths import MEM0_DIR
from ...services import settings_store
from ...services.llm import _parse_json_blob

KIND_CN = {
    "preference": "偏好",
    "person": "人物",
    "event": "事件",
    "open_loop": "未完",
    "trait": "性格",
}
VALID_KINDS = tuple(KIND_CN)
MAX_INJECT = 8
_CAT_TO_KIND = {
    "user_preferences": "preference",
    "preferences": "preference",
    "personal_details": "person",
    "personal_info": "person",
    "relationships": "person",
    "life_events": "event",
    "events": "event",
    "tasks": "open_loop",
    "goals": "open_loop",
    "personality": "trait",
    "traits": "trait",
}
_PERSONAL_CATS = {
    "personal_details", "personal_info", "relationships", "person",
}
_EXTRACT_HINT = (
    "用中文抽取值得长期记住的事实：对方姓名、称呼、偏好、关系、约定、重要经历、性格习惯。"
    "写成短句陈述。姓名写成「用户的名字是X」。"
    "不要记录问句、寒暄、跳舞点播、剧照短片、重复称呼、口头禅。"
    "没有可记的事实就不要输出。"
)
_PERF_TAG_RE = re.compile(r"\[(?:emo|act|dance|cam):[^\]]*\]")

_lock = threading.RLock()
_cache: Dict[str, Any] = {"key": None, "llm_key": None, "mem": None, "migrated": False, "embed_sig": ""}
_minilm_probe: Dict[str, Any] = {"tried": False, "emb": None}
_IDENTITY_RE = re.compile(r"(用户的名字是|她的名字是|对方的名字是)")
_PROBE_MODELS = (
    "text-embedding-v3",
    "text-embedding-v4",
    "text-embedding-v2",
    "text-embedding-3-small",
    "embedding-3",
    "doubao-embedding",
    "doubao-embedding-large",
    "doubao-embedding-large-text-240915",
    "doubao-embedding-text-240515",
)
_embed_cache: Dict[str, Any] = {"key": None, "emb": None}
_MARKER = MEM0_DIR / "embedder.txt"


def _uid(character_id: int) -> str:
    return f"companion-char-{int(character_id)}"


def _now() -> datetime:
    return datetime.utcnow()


def _results(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, dict):
        items = raw.get("results")
        if items is None:
            items = raw.get("memories")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


class RemoteEmbedder:
    """走当前 LLM 网关的 /embeddings，不进 sentence-transformers，免得和 TTS 抢包。"""

    @classmethod
    def probe(cls, llm_conf: Dict[str, Any]) -> Optional["RemoteEmbedder"]:
        api_key = (llm_conf.get("api_key") or "").strip()
        base_url = (llm_conf.get("base_url") or "").rstrip("/")
        cache_key = (api_key, base_url)
        if _embed_cache["key"] == cache_key:
            return _embed_cache["emb"]
        found: Optional["RemoteEmbedder"] = None
        if api_key and base_url:
            found = cls._probe_compat(api_key, base_url)
            if found is None and "dashscope" in base_url:
                found = cls._probe_dashscope_native(api_key)
        _embed_cache["key"] = cache_key
        _embed_cache["emb"] = found
        return found

    @classmethod
    def _probe_compat(cls, api_key: str, base_url: str) -> Optional["RemoteEmbedder"]:
        last = ""
        with httpx.Client(timeout=httpx.Timeout(12, connect=6), trust_env=False) as client:
            for model in _PROBE_MODELS:
                for payload in (
                    {"model": model, "input": "记忆召回探测"},
                    {"model": model, "input": ["记忆召回探测"]},
                ):
                    try:
                        resp = client.post(
                            f"{base_url}/embeddings",
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
                        print(f"[memory] embedder {model} dim={len(vec)}")
                        emb = cls(api_key, base_url, model, len(vec))
                        emb._input_list = isinstance(payload["input"], list)
                        return emb
        print(f"[memory] compatible embeddings failed: {last}")
        return None

    @classmethod
    def _probe_dashscope_native(cls, api_key: str) -> Optional["RemoteEmbedder"]:
        url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        with httpx.Client(timeout=httpx.Timeout(12, connect=6), trust_env=False) as client:
            for model in ("text-embedding-v3", "text-embedding-v2", "text-embedding-v1"):
                try:
                    resp = client.post(
                        url,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": model, "input": {"texts": ["记忆召回探测"]}, "parameters": {"text_type": "query"}},
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
                    print(f"[memory] dashscope native embedder {model} dim={len(vec)}")
                    emb = cls(api_key, url, model, len(vec))
                    emb._native = True
                    return emb
        return None

    def __init__(self, api_key: str, base_url: str, model: str, dims: int):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dims = dims
        self._input_list = False
        self._native = False
        self.config = type("Cfg", (), {"embedding_dims": dims, "model": model})()

    def _post(self, texts: List[str]) -> List[List[float]]:
        blob = [(t or "").strip() or " " for t in texts]
        with httpx.Client(timeout=httpx.Timeout(30, connect=8), trust_env=False) as client:
            if self._native:
                resp = client.post(
                    self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={"model": self.model, "input": {"texts": blob}, "parameters": {"text_type": "query"}},
                )
                resp.raise_for_status()
                rows = resp.json()["output"]["embeddings"]
                rows = sorted(rows, key=lambda x: x.get("text_index", 0))
                return [row["embedding"] for row in rows]
            payload: Dict[str, Any] = {"model": self.model, "input": blob if self._input_list else blob[0]}
            if len(blob) > 1:
                payload["input"] = blob
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


_LOCAL_MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_LOCAL_MINILM_DIMS = 384


def _minilm_local_dir() -> Optional[str]:
    """直接用 HF 缓存里的 snapshot 目录，避免 from_pretrained(repo_id) 去打 huggingface.co。"""
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
        has_weight = (snap / "model.safetensors").is_file() or (snap / "pytorch_model.bin").is_file()
        if has_weight and (snap / "config.json").is_file():
            return key
    return None


class LocalMiniLMEmbedder:
    """本机已缓存的 MiniLM。只用 transformers 4.57，不装 sentence-transformers，避免把 TTS 升坏。CPU 推理。"""

    def __init__(self, model, tokenizer, torch_mod):
        self.model = model
        self.tok = tokenizer
        self.torch = torch_mod
        self.dims = _LOCAL_MINILM_DIMS
        self.model_name = "minilm"
        self.config = type("Cfg", (), {"embedding_dims": self.dims, "model": "minilm"})()
        self._gate = threading.Lock()

    @classmethod
    def probe(cls) -> Optional["LocalMiniLMEmbedder"]:
        if _minilm_probe["tried"]:
            return _minilm_probe["emb"]
        local = _minilm_local_dir()
        if not local:
            print("[memory] MiniLM weights missing in HF cache")
            _minilm_probe["tried"] = True
            return None
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:
            print(f"[memory] MiniLM import fail: {exc}")
            _minilm_probe["tried"] = True
            return None
        prev = {k: os.environ.get(k) for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            tok = AutoTokenizer.from_pretrained(local, local_files_only=True)
            # TTS 加载过 accelerate 后，默认 low_cpu_mem_usage 会把权重放到 meta，
            # 再 .to("cpu") 就会炸。关这个开关，老老实实进 CPU。
            model = AutoModel.from_pretrained(
                local, local_files_only=True, low_cpu_mem_usage=False,
            )
            model.eval()
            for p in model.parameters():
                p.requires_grad_(False)
            if next(model.parameters()).device.type != "cpu":
                model.to("cpu")
            dummy = tok("ping", return_tensors="pt")
            with torch.no_grad():
                hid = model(**dummy).last_hidden_state
            if hid.shape[-1] != _LOCAL_MINILM_DIMS:
                print(f"[memory] MiniLM unexpected dim={hid.shape[-1]}")
            print("[memory] local MiniLM ready dim=384 (cpu)")
            emb = cls(model, tok, torch)
            _minilm_probe["emb"] = emb
            _minilm_probe["tried"] = True
            return emb
        except Exception as exc:
            print(f"[memory] MiniLM load fail: {exc}")
            _minilm_probe["tried"] = True
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
            with self.torch.no_grad():
                hidden = self.model(**enc).last_hidden_state
                mask = enc["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
                pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                pooled = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
            return pooled.cpu().tolist()


class _HashingEmbedder:
    """只用来把旧的 hashing 库读出来，再迁到真向量。"""

    def __init__(self, dims: int = 384):
        self.dims = dims
        self.config = type("Cfg", (), {"embedding_dims": dims, "model": "hashing-ngram"})()

    def embed(self, text, memory_action=None):
        vec = [0.0] * self.dims
        t = (text or "").strip() or " "
        grams = [t[i:i + 2] for i in range(len(t) - 1)] or [t]
        for g in grams:
            h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dims] += 1.0
            vec[(h >> 10) % self.dims] -= 0.35
        n = sum(x * x for x in vec) ** 0.5
        if n < 1e-8:
            return vec
        return [x / n for x in vec]

    def embed_batch(self, texts, memory_action="add"):
        return [self.embed(t, memory_action) for t in texts]


def _mem0_config(llm_conf: Dict[str, Any], *, dims: int, collection: str) -> Dict[str, Any]:
    api_key = llm_conf.get("api_key") or ""
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    model = llm_conf.get("model") or "qwen-plus"
    (MEM0_DIR / "qdrant").mkdir(parents=True, exist_ok=True)
    return {
        "llm": {
            "provider": "openai",
            "config": {
                "model": model,
                "temperature": 0.1,
                "max_tokens": 1200,
                "api_key": api_key,
                "openai_base_url": base_url,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": api_key or "local",
                "openai_base_url": base_url or "http://127.0.0.1",
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": collection,
                "embedding_model_dims": dims,
                "path": str(MEM0_DIR / "qdrant"),
                "on_disk": True,
            },
        },
        "history_db_path": str(MEM0_DIR / "history.db"),
        "custom_instructions": _EXTRACT_HINT,
    }


def _close_mem(mem) -> None:
    if mem is None:
        return
    try:
        vs = getattr(mem, "vector_store", None)
        client = getattr(vs, "client", None) if vs is not None else None
        if client is not None and hasattr(client, "close"):
            client.close()
    except Exception:
        pass


def _dump_collection(mem, character_ids: Sequence[int]) -> List[Dict[str, Any]]:
    dump: List[Dict[str, Any]] = []
    for cid in character_ids:
        if not cid:
            continue
        for item in _get_all(mem, _uid(cid), top_k=200):
            text = _item_text(item)
            if not text:
                continue
            dump.append({
                "character_id": int(cid),
                "text": text,
                "meta": dict(_item_meta(item)),
            })
    return dump


def _is_identity_fact(text: str) -> bool:
    return bool(_IDENTITY_RE.search((text or "").strip()))


def _pin_identity(row: Dict[str, Any]) -> Dict[str, Any]:
    meta = dict(row.get("meta") or {})
    meta["pinned"] = True
    meta["kind"] = "person"
    return {**row, "meta": meta}


def _cull_facts(llm_conf: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """一次性让模型丢掉问句、剧照、点舞、重复称呼。姓名类事实代码侧强制保留。"""
    if not rows:
        return []
    numbered = "\n".join(f"{i + 1}. {r['text'][:100]}" for i, r in enumerate(rows))
    api_key = (llm_conf.get("api_key") or "").strip()
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    if not api_key or not base_url:
        return rows
    payload = {
        "model": llm_conf.get("model") or "qwen-plus",
        "temperature": 0.1,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "清理陪伴 AI 的长期记忆。只保留对以后聊天有用的事实。"
                    "丢掉问句、寒暄、跳舞点播、剧照短片、重复称呼、口头禅。"
                    "用户姓名必须保留。只输出 JSON："
                    '{"keep":[序号],"pin":[姓名或身份类序号]}'
                ),
            },
            {"role": "user", "content": numbered},
        ],
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(60, connect=10), trust_env=False) as client:
            resp = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        if resp.status_code != 200:
            print(f"[memory] cull HTTP {resp.status_code}")
            return rows
        raw = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        data = _parse_json_blob(raw) or {}
        keep = {int(x) for x in (data.get("keep") or []) if str(x).isdigit()}
        pin = {int(x) for x in (data.get("pin") or []) if str(x).isdigit()}
    except Exception as exc:
        print(f"[memory] cull failed: {exc}")
        return rows
    if not keep:
        print("[memory] cull returned empty, keep original")
        keep = set(range(1, len(rows) + 1))
        pin = set()
    out = []
    kept_texts = set()
    for i, row in enumerate(rows, start=1):
        text = (row.get("text") or "").strip()
        identity = _is_identity_fact(text)
        if i not in keep and not identity:
            continue
        if identity:
            row = _pin_identity(row)
        else:
            meta = dict(row.get("meta") or {})
            if i in pin:
                meta["pinned"] = True
                meta["kind"] = "person"
            row = {**row, "meta": meta}
        out.append(row)
        kept_texts.add(text)
    for row in rows:
        text = (row.get("text") or "").strip()
        if _is_identity_fact(text) and text not in kept_texts:
            out.insert(0, _pin_identity(row))
            kept_texts.add(text)
    print(f"[memory] cull {len(rows)} -> {len(out)}")
    return out


def _restore_dump(mem, rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        text = (row.get("text") or "").strip()
        cid = int(row.get("character_id") or 0)
        if not text or not cid:
            continue
        md = dict(row.get("meta") or {})
        md.setdefault("kind", "event")
        md.setdefault("source", "reindex")
        try:
            mem.add(text, user_id=_uid(cid), infer=False, metadata=md)
        except Exception as exc:
            print(f"[memory] reindex skip: {exc}")


def _dump_hashing_store(session: Session, llm_conf: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = [c.id for c in session.exec(select(Character)).all() if c.id]
    try:
        from mem0 import Memory
        legacy = Memory.from_config(_mem0_config(llm_conf, dims=384, collection="companion_384"))
        legacy.embedding_model = _HashingEmbedder(384)
        dump = _dump_collection(legacy, ids)
        _close_mem(legacy)
        print(f"[memory] dumped hashing store n={len(dump)}")
        return dump
    except Exception as exc:
        print(f"[memory] hashing dump skip: {exc}")
        return []


def _rebuild_index(mem, llm_conf: Dict[str, Any], dump: List[Dict[str, Any]], ids: Sequence[int]) -> None:
    kept = _cull_facts(llm_conf, dump)
    for cid in ids:
        if not cid:
            continue
        for item in _get_all(mem, _uid(cid), top_k=200):
            rid = item.get("id")
            if rid:
                try:
                    mem.delete(str(rid))
                except Exception:
                    pass
    _restore_dump(mem, kept)
    print(f"[memory] reindexed n={len(kept)}")


def _client(session: Session):
    conf = settings_store.get_all(session).get("llm") or {}
    api_key = (conf.get("api_key") or "").strip()
    if not api_key:
        return None
    llm_key = (api_key, conf.get("base_url") or "", conf.get("model") or "")
    with _lock:
        if _cache["mem"] is not None and _cache.get("llm_key") == llm_key:
            return _cache["mem"]
    embedder = RemoteEmbedder.probe(conf)
    if embedder is None:
        embedder = LocalMiniLMEmbedder.probe()
    sig = f"{getattr(embedder, 'model_name', getattr(embedder, 'model', 'none'))}:{getattr(embedder, 'dims', 0)}"
    key = (api_key, conf.get("base_url") or "", conf.get("model") or "", sig)
    with _lock:
        if _cache["mem"] is not None and _cache["key"] == key:
            _cache["llm_key"] = llm_key
            return _cache["mem"]
        os.environ["MEM0_TELEMETRY"] = "False"
        os.environ["OPENAI_API_KEY"] = api_key
        base_url = (conf.get("base_url") or "").rstrip("/")
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url
        _close_mem(_cache.get("mem"))
        _cache["mem"] = None
        try:
            from mem0 import Memory
            if embedder is None:
                print("[memory] no embedding API and no local MiniLM; facts still stored, recall uses LLM")
                cfg = _mem0_config(conf, dims=384, collection="companion_384")
                mem = Memory.from_config(cfg)
                mem.embedding_model = _HashingEmbedder(384)
                ids = [c.id for c in session.exec(select(Character)).all() if c.id]
                old = ""
                try:
                    old = _MARKER.read_text(encoding="utf-8").strip()
                except OSError:
                    old = ""
                if old != "hashing-llm":
                    dump = _dump_collection(mem, ids)
                    _rebuild_index(mem, conf, dump, ids)
                    try:
                        _MARKER.write_text("hashing-llm", encoding="utf-8")
                    except OSError:
                        pass
                _cache["semantic"] = False
            else:
                coll = f"companion_{sig.replace(':', '_')}"
                old = ""
                try:
                    old = _MARKER.read_text(encoding="utf-8").strip()
                except OSError:
                    old = ""
                dump: Optional[List[Dict[str, Any]]] = None
                if old != sig:
                    dump = _dump_hashing_store(session, conf)
                cfg = _mem0_config(conf, dims=int(embedder.dims), collection=coll)
                mem = Memory.from_config(cfg)
                mem.embedding_model = embedder
                ids = [c.id for c in session.exec(select(Character)).all() if c.id]
                if old != sig:
                    if not dump:
                        dump = _dump_collection(mem, ids)
                    _rebuild_index(mem, conf, dump, ids)
                    try:
                        _MARKER.write_text(sig, encoding="utf-8")
                    except OSError:
                        pass
                    print(f"[memory] index {old or 'empty'} -> {sig}")
                _cache["semantic"] = True
        except Exception as exc:
            print(f"[memory] mem0 init failed: {exc}")
            return None
        _cache["key"] = key
        _cache["llm_key"] = llm_key
        _cache["mem"] = mem
        _cache["embed_sig"] = sig
        return mem


def warmup(session: Session) -> None:
    mem = _client(session)
    print("[memory] mem0 ready" if mem is not None else "[memory] mem0 unavailable")


def _item_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    md = item.get("metadata")
    if not isinstance(md, dict):
        md = item.get("payload")
    return md if isinstance(md, dict) else {}


def _item_text(item: Dict[str, Any]) -> str:
    return str(item.get("memory") or item.get("text") or item.get("data") or "").strip()


def _item_kind(item: Dict[str, Any]) -> str:
    md = _item_meta(item)
    kind = str(md.get("kind") or "").strip()
    if kind in VALID_KINDS:
        return kind
    cats = item.get("categories") or md.get("categories") or []
    if isinstance(cats, str):
        cats = [cats]
    if isinstance(cats, list):
        for c in cats:
            mapped = _CAT_TO_KIND.get(str(c).strip().lower())
            if mapped:
                return mapped
    return "event"


def fact_to_dict(item: Dict[str, Any], character_id: int) -> Dict[str, Any]:
    md = _item_meta(item)
    kind = _item_kind(item)
    try:
        importance = float(md.get("importance") if md.get("importance") is not None else 0.5)
    except (TypeError, ValueError):
        importance = 0.5
    return {
        "id": str(item.get("id") or ""),
        "character_id": character_id,
        "kind": kind,
        "kind_cn": KIND_CN.get(kind, kind or "记忆"),
        "content": _item_text(item),
        "importance": max(0.0, min(1.0, importance)),
        "pinned": bool(md.get("pinned")),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
    }


def _legacy_to_dict(row: MemoryFact) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "character_id": row.character_id,
        "kind": row.kind,
        "kind_cn": KIND_CN.get(row.kind, row.kind),
        "content": row.content,
        "importance": row.importance,
        "pinned": bool(row.pinned),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def _get_all(mem, uid: str, top_k: int = 100) -> List[Dict[str, Any]]:
    try:
        raw = mem.get_all(filters={"user_id": uid}, top_k=top_k)
    except TypeError:
        try:
            raw = mem.get_all(user_id=uid, limit=top_k)
        except TypeError:
            raw = mem.get_all(user_id=uid)
    return _results(raw)


def _search(mem, query: str, uid: str, top_k: int = 12) -> List[Dict[str, Any]]:
    try:
        raw = mem.search(query, filters={"user_id": uid}, top_k=top_k, threshold=0.2)
    except TypeError:
        try:
            raw = mem.search(query, user_id=uid, limit=top_k)
        except TypeError:
            raw = mem.search(query, user_id=uid)
    return _results(raw)


def _migrate_sqlite(session: Session, mem) -> None:
    if _cache.get("migrated"):
        return
    rows = list(session.exec(select(MemoryFact)).all())
    if not rows:
        _cache["migrated"] = True
        return
    for row in rows:
        content = (row.content or "").strip()
        if not content:
            session.delete(row)
            continue
        try:
            mem.add(
                content,
                user_id=_uid(row.character_id),
                infer=False,
                metadata={
                    "kind": row.kind if row.kind in VALID_KINDS else "event",
                    "pinned": bool(row.pinned),
                    "importance": float(row.importance or 0.5),
                    "migrated": True,
                },
            )
            session.delete(row)
        except Exception as exc:
            print(f"[memory] migrate skip id={row.id}: {exc}")
    session.commit()
    leftover = session.exec(select(MemoryFact).limit(1)).first()
    _cache["migrated"] = True
    if leftover is None:
        print("[memory] sqlite facts migrated into mem0")
    else:
        print("[memory] sqlite facts remain; panel will show both until they migrate")


def list_facts(session: Session, character_id: int) -> List[Dict[str, Any]]:
    mem = _client(session)
    if mem is not None:
        with _lock:
            _migrate_sqlite(session, mem)
            try:
                items = _get_all(mem, _uid(character_id), top_k=120)
            except Exception as exc:
                print(f"[memory] get_all failed: {exc}")
                items = []
        pinned = [x for x in items if _item_meta(x).get("pinned") and _item_text(x)]
        rest = [x for x in items if not _item_meta(x).get("pinned") and _item_text(x)]
        rest.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
        out = [fact_to_dict(x, character_id) for x in pinned + rest]
        rows = list(session.exec(
            select(MemoryFact)
            .where(MemoryFact.character_id == character_id)
            .order_by(MemoryFact.pinned.desc(), MemoryFact.importance.desc(),
                      MemoryFact.updated_at.desc())
        ).all())
        legacy = [_legacy_to_dict(r) for r in rows]
        if not legacy:
            return out
        seen = {r.get("content") for r in out}
        return out + [r for r in legacy if r.get("content") not in seen]
    rows = list(session.exec(
        select(MemoryFact)
        .where(MemoryFact.character_id == character_id)
        .order_by(MemoryFact.pinned.desc(), MemoryFact.importance.desc(),
                  MemoryFact.updated_at.desc())
    ).all())
    return [_legacy_to_dict(r) for r in rows]


def inject_memory(
    session: Session,
    character_id: int,
    messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    query = _last_user_text(messages)
    t0 = time.perf_counter()
    picked = _retrieve(session, character_id, query)
    ms = int((time.perf_counter() - t0) * 1000)
    if not picked:
        print(f"[memory] inject empty q={query[:40]!r} {ms}ms")
        return messages
    lines = []
    seen = set()
    for r in picked:
        text = (r.get("content") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        pin = "（置顶）" if r.get("pinned") else ""
        lines.append(f"- [{r.get('kind_cn') or r.get('kind')}]{pin}{text}")
    block = (
        "长期记忆（向量召回，比刚才几句对话更准；你若刚说过不知道，以这里为准）：\n"
        + "\n".join(lines)
        + "\n对方问起自己是谁、叫什么、以前聊过什么，用这些事实回答，不要让对方再说一遍。"
        "不要把清单念出来。用户说「历史/记得」时，先当成你们的交往，不是古代史，除非在谈书。"
    )
    print(
        "[memory] inject n="
        + str(len(lines))
        + f" {ms}ms q="
        + repr(query[:40])
        + " -> "
        + " | ".join(x[:18] for x in seen)
    )
    out = list(messages)
    insert_at = 1 if out and out[0].get("role") == "system" else 0
    out.insert(insert_at, {"role": "system", "content": block})
    return out


def _last_user_text(messages: Sequence[Dict[str, str]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


def _llm_pick(
    llm_conf: Dict[str, Any],
    query: str,
    items: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    if not items:
        return []
    numbered = "\n".join(f"{i + 1}. {_item_text(x)[:80]}" for i, x in enumerate(items[:40]))
    api_key = (llm_conf.get("api_key") or "").strip()
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    if not api_key or not base_url:
        return items[:top_k]
    payload = {
        "model": llm_conf.get("model") or "qwen-plus",
        "temperature": 0.1,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "根据用户这句话，从记忆列表里挑出真正相关的长期事实。"
                    f"最多 {top_k} 条。只输出 JSON：{{\"pick\":[序号]}}"
                ),
            },
            {"role": "user", "content": f"用户说：{query[:200]}\n\n记忆：\n{numbered}"},
        ],
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(30, connect=8), trust_env=False) as client:
            resp = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        if resp.status_code != 200:
            return items[:top_k]
        data = _parse_json_blob((resp.json()["choices"][0]["message"].get("content") or "").strip()) or {}
        pick = [int(x) for x in (data.get("pick") or []) if str(x).isdigit()]
    except Exception as exc:
        print(f"[memory] llm pick failed: {exc}")
        return items[:top_k]
    out = []
    for n in pick:
        if 1 <= n <= min(40, len(items)):
            out.append(items[n - 1])
        if len(out) >= top_k:
            break
    return out or items[:top_k]


def _retrieve(session: Session, character_id: int, query: str) -> List[Dict[str, Any]]:
    mem = _client(session)
    if mem is None:
        rows = list_facts(session, character_id)
        return [r for r in rows if r.get("pinned")][:MAX_INJECT]
    uid = _uid(character_id)
    q = (query or "").strip() or "对方是谁，有什么偏好、约定和还没做完的事"
    conf = settings_store.get_all(session).get("llm") or {}
    try:
        with _lock:
            _migrate_sqlite(session, mem)
            all_items = _get_all(mem, uid, top_k=80)
            if not all_items:
                searched: List[Dict[str, Any]] = []
            elif _cache.get("semantic"):
                searched = _search(mem, q, uid, top_k=MAX_INJECT)
            else:
                searched = _llm_pick(conf, q, all_items, MAX_INJECT)
        pinned = [x for x in all_items if _item_meta(x).get("pinned") and _item_text(x)]
        picked: List[Dict[str, Any]] = []
        seen = set()
        for item in pinned + searched:
            rid = str(item.get("id") or "")
            text = _item_text(item)
            if not rid or not text or rid in seen:
                continue
            picked.append(fact_to_dict(item, character_id))
            seen.add(rid)
            if len(picked) >= MAX_INJECT:
                break
        return picked
    except Exception as exc:
        print(f"[memory] retrieve failed: {exc}")
        return []


def scene_hints(session: Session, character_id: int) -> List[str]:
    mem = _client(session)
    if mem is None:
        return []
    try:
        with _lock:
            items = _search(mem, "未完的约定、下次要做的事、最近发生的事", _uid(character_id), top_k=4)
    except Exception as exc:
        print(f"[memory] scene search failed: {exc}")
        return []
    return [t for t in (_item_text(x) for x in items) if t][:4]


def retrieve_facts(session: Session, character_id: int, query: str) -> List[Dict[str, Any]]:
    return _retrieve(session, character_id, query)


def strip_perf(text: str) -> str:
    return _PERF_TAG_RE.sub("", text or "").strip()


def llm_extract_facts(llm_conf: Dict[str, Any], messages: List[Dict[str, str]]) -> List[str]:
    """只打抽取 LLM，不碰向量库。空结果也合法。"""
    api_key = (llm_conf.get("api_key") or "").strip()
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    if not api_key or not base_url or not messages:
        return []
    lines = []
    for m in messages:
        role = "用户" if m.get("role") == "user" else "助手"
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{role}：{content}")
    blob = "\n".join(lines)[:8000]
    if not blob.strip():
        return []
    payload = {
        "model": llm_conf.get("model") or "qwen-plus",
        "temperature": 0.1,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    _EXTRACT_HINT
                    + '只输出 JSON：{"facts":["短句",...]}。没有可记的事实就 {"facts":[]}。'
                ),
            },
            {"role": "user", "content": blob},
        ],
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(60, connect=8), trust_env=False) as client:
            resp = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        if resp.status_code != 200:
            print(f"[memory] extract llm HTTP {resp.status_code}")
            return []
        text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        data = _parse_json_blob(text) or {}
        facts = data.get("facts") if isinstance(data, dict) else data
        if not isinstance(facts, list):
            return []
        out: List[str] = []
        seen = set()
        for item in facts:
            fact = str(item or "").strip()
            if len(fact) < 4 or fact in seen:
                continue
            seen.add(fact)
            out.append(fact[:400])
        return out
    except Exception as exc:
        print(f"[memory] extract llm failed: {exc}")
        return []


def store_extracted_facts(session: Session, character_id: int, facts: List[str]) -> int:
    mem = _client(session)
    if mem is None:
        n = 0
        for fact in facts:
            _legacy_upsert(session, character_id, fact_id=None, kind="event",
                           content=fact, importance=0.5, pinned=None)
            n += 1
        return n
    added: List[Dict[str, Any]] = []
    with _lock:
        _migrate_sqlite(session, mem)
        for fact in facts:
            raw = mem.add(
                fact,
                user_id=_uid(character_id),
                infer=False,
                metadata={"source": "chat", "kind": "event"},
            )
            added.extend(_results(raw))
        _pin_extracted(mem, added)
    return len(added)


def _pin_extracted(mem, added: List[Dict[str, Any]]) -> None:
    for item in added:
        rid = item.get("id")
        if not rid:
            continue
        cats = item.get("categories") or _item_meta(item).get("categories") or []
        if isinstance(cats, str):
            cats = [cats]
        cat_l = {str(c).strip().lower() for c in cats if c}
        kind = "person" if (cat_l & _PERSONAL_CATS) else _item_kind(item)
        pinned = bool(cat_l & _PERSONAL_CATS) or kind == "person"
        if not pinned:
            continue
        md = dict(_item_meta(item))
        md.update({"kind": kind, "pinned": True, "source": "chat"})
        try:
            mem.update(str(rid), metadata=md)
        except Exception:
            pass


def upsert_fact(session: Session, character_id: int, *,
                fact_id: Optional[str] = None,
                kind: str = "event",
                content: str = "",
                importance: float = 0.5,
                pinned: Optional[bool] = None) -> Dict[str, Any]:
    content = (content or "").strip()
    if kind not in VALID_KINDS:
        kind = "event"
    try:
        importance = max(0.0, min(1.0, float(importance)))
    except (TypeError, ValueError):
        importance = 0.5
    mem = _client(session)
    if mem is None:
        return _legacy_upsert(session, character_id, fact_id=fact_id, kind=kind,
                              content=content, importance=importance, pinned=pinned)
    uid = _uid(character_id)
    md: Dict[str, Any] = {"kind": kind, "importance": importance, "source": "manual"}
    if pinned is not None:
        md["pinned"] = bool(pinned)
    with _lock:
        _migrate_sqlite(session, mem)
        if fact_id:
            existing = None
            for item in _get_all(mem, uid, top_k=120):
                if str(item.get("id")) == str(fact_id):
                    existing = item
                    break
            if existing is None:
                raise KeyError("fact not found")
            old_md = dict(_item_meta(existing))
            old_md.update(md)
            kwargs: Dict[str, Any] = {"metadata": old_md}
            if content:
                kwargs["text"] = content
            try:
                mem.update(str(fact_id), **kwargs)
            except TypeError:
                mem.update(str(fact_id), data=content or _item_text(existing))
            for item in _get_all(mem, uid, top_k=120):
                if str(item.get("id")) == str(fact_id):
                    return fact_to_dict(item, character_id)
            return {
                "id": str(fact_id),
                "character_id": character_id,
                "kind": kind,
                "kind_cn": KIND_CN.get(kind, kind),
                "content": content or _item_text(existing),
                "importance": importance,
                "pinned": bool(old_md.get("pinned")),
                "created_at": "",
                "updated_at": "",
            }
        raw = mem.add(
            content,
            user_id=uid,
            infer=False,
            metadata=md if pinned is not None else {**md, "pinned": False},
        )
    added = _results(raw)
    if added:
        item = added[0]
        if not item.get("memory"):
            item = {**item, "memory": content, "metadata": md}
        return fact_to_dict(item, character_id)
    return {
        "id": "",
        "character_id": character_id,
        "kind": kind,
        "kind_cn": KIND_CN.get(kind, kind),
        "content": content,
        "importance": importance,
        "pinned": bool(pinned),
        "created_at": "",
        "updated_at": "",
    }


def _legacy_upsert(session: Session, character_id: int, *,
                   fact_id: Optional[str], kind: str, content: str,
                   importance: float, pinned: Optional[bool]) -> Dict[str, Any]:
    now = _now()
    row: Optional[MemoryFact] = None
    if fact_id and str(fact_id).isdigit():
        row = session.get(MemoryFact, int(fact_id))
        if row and row.character_id != character_id:
            row = None
    if row is None:
        if not content:
            raise ValueError("content required")
        row = MemoryFact(character_id=character_id, created_at=now)
        session.add(row)
    row.kind = kind
    if content:
        row.content = content
    row.importance = importance
    if pinned is not None:
        row.pinned = pinned
    row.updated_at = now
    session.commit()
    session.refresh(row)
    return _legacy_to_dict(row)


def delete_fact(session: Session, character_id: int, fact_id: str) -> bool:
    mem = _client(session)
    if mem is not None:
        with _lock:
            try:
                mem.delete(str(fact_id))
                return True
            except Exception:
                pass
    if str(fact_id).isdigit():
        row = session.get(MemoryFact, int(fact_id))
        if not row or row.character_id != character_id:
            return False
        session.delete(row)
        session.commit()
        return True
    return False


def add_event_note(session: Session, character_id: int, content: str) -> Dict[str, Any]:
    """剧照不再写入记忆。保留空实现以免旧调用报错。"""
    return {
        "id": "",
        "character_id": character_id,
        "kind": "event",
        "kind_cn": KIND_CN["event"],
        "content": (content or "").strip(),
        "importance": 0.0,
        "pinned": False,
        "created_at": "",
        "updated_at": "",
    }
