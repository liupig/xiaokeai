"""记忆：LLM 抽长期事实，SQLite 为真相源，mem0 只做向量索引。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from sqlmodel import Session, select

from ...models import Character, ChatMessage, MemoryEpisode, MemoryFact, PinnedMessage, utc_now
from ...paths import MEM0_DIR
from ...services import settings_store
from . import embedder as embed_svc
from . import rank
from ...services.llm import _parse_json_blob

os.environ["MEM0_TELEMETRY"] = "False"

KIND_CN = {
    "preference": "偏好",
    "person": "人物",
    "event": "事件",
    "open_loop": "未完",
    "trait": "性格",
}
_EMO_CN = {
    "angry": "生气",
    "sad": "伤心",
    "happy": "高兴",
}
VALID_KINDS = tuple(KIND_CN)
MAX_INJECT = rank.MAX_FACT_INJECT
_CANDIDATES = 20
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
    "写成短句陈述。姓名写成「用户的名字是X」。宠物、称呼也标 person。"
    "偏好标 preference，发生过的事标 event，性格习惯标 trait。"
    "open_loop 只记双方说定、还没做的具体的事，时间地点照对方原话，不要改。"
    "不要记问句、寒暄、跳舞点播、口头禅，也不要记「随时喊我」「想喝水」「去买奶茶」这种随口客套。"
    "助手自己发挥、用户没说过的计划，不要记。"
    "没有可记的事实就不要输出。"
)
_EXTRACT_TAIL = (
    "每条带来源句的序号 n（对应用户消息列表里的编号）。"
    "生气或伤心的事件再加 emotion，只能是 angry 或 sad，没有就空字符串。"
    "只输出 JSON："
    '{"facts":[{"text":"短句","kind":"event","n":1,"emotion":""}]}。'
    '没有可记的事实就 {"facts":[]}。'
)
_EPISODE_HINT = (
    "把这段对话收成两三句以后能想起来的经历。"
    "只写用户亲口说过的事、情绪和约定。时间词照原话。"
    "助手接着添的安排不要写。不要补对方没说的星期和钟点。"
    "不要写成偏好清单。发呆、喝水、无聊、随时喊我这类客套不要写进去。"
    '只输出 JSON：{"summary":"两三句"}。没什么可记就 {"summary":""}。'
)
_PERF_TAG_RE = re.compile(r"\[(?:emo|act|dance|cam):[^\]]*\]")

_lock = threading.RLock()
_cache: Dict[str, Any] = {
    "key": None, "llm_key": None, "mem": None, "imported": False, "embed_sig": "",
}
_IDENTITY_RE = re.compile(r"(用户的名字是|她的名字是|对方的名字是)")


def _extract_hint() -> str:
    from ...locale_pack import prompts
    mem = prompts().get("memory") or {}
    return str(mem.get("extract") or _EXTRACT_HINT)


def _extract_tail() -> str:
    from ...locale_pack import prompts
    mem = prompts().get("memory") or {}
    return str(mem.get("json_tail") or _EXTRACT_TAIL)


def _episode_hint() -> str:
    from ...locale_pack import prompts
    mem = prompts().get("memory") or {}
    return str(mem.get("episode") or _EPISODE_HINT)


def _identity_re():
    from ...locale_pack import prompts
    mem = prompts().get("memory") or {}
    pat = str(mem.get("identity") or _IDENTITY_RE.pattern)
    if pat == _IDENTITY_RE.pattern:
        return _IDENTITY_RE
    return re.compile(f"(?:{pat})|(?:{_IDENTITY_RE.pattern})")
_MARKER = MEM0_DIR / "embedder.txt"
_IMPORTED = MEM0_DIR / "facts_imported.txt"


def _uid(character_id: int) -> str:
    return f"companion-char-{int(character_id)}"


def _now() -> datetime:
    return utc_now()


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


class _HashingEmbedder:
    """只用来把旧的 hashing 库读出来，再迁到 SQLite。"""

    def __init__(self, dims: int = 384):
        self.dims = dims
        self.provider = "hashing"
        self.model_name = "hashing-ngram"
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
        "custom_instructions": _extract_hint(),
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


_mem0_optional_patched = False


def _patch_mem0_optional() -> None:
    """离线包不装 spaCy / 不下载 Qdrant BM25。语义向量照常，关键词混合搜索关掉。"""
    global _mem0_optional_patched
    os.environ["MEM0_TELEMETRY"] = "False"
    if _mem0_optional_patched:
        return
    _mem0_optional_patched = True
    try:
        import mem0.utils.spacy_models as spacy_models
        spacy_models._load_failed_full = True
        spacy_models._load_failed_lemma = True
    except Exception:
        pass
    try:
        import mem0.utils.lemmatization as lemma
        lemma.lemmatize_for_bm25 = lambda text: text or ""
    except Exception:
        pass


def _disable_mem0_bm25(mem) -> None:
    vs = getattr(mem, "vector_store", None)
    if vs is None:
        return
    try:
        vs._has_bm25_slot = False
        vs._bm25_encoder = False
    except Exception:
        pass


def _mem0_from_config(cfg: Dict[str, Any]):
    _patch_mem0_optional()
    from mem0 import Memory
    mem = Memory.from_config(cfg)
    _disable_mem0_bm25(mem)
    return mem


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
    return bool(_identity_re().search((text or "").strip()))


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


def _character_ids(session: Session) -> List[int]:
    return [c.id for c in session.exec(select(Character)).all() if c.id]


def _read_marker() -> str:
    try:
        return _MARKER.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_marker(sig: str) -> None:
    try:
        MEM0_DIR.mkdir(parents=True, exist_ok=True)
        _MARKER.write_text(sig, encoding="utf-8")
    except OSError:
        pass


def _legacy_collections(sig: str) -> List[Tuple[str, int]]:
    """旧 collection 名 + 维度，只为把文本倒进 SQLite。"""
    out: List[Tuple[str, int]] = [("companion_384", 384)]
    seen = {out[0][0]}
    if not sig:
        return out
    coll = embed_svc.collection_name(sig)
    dims = 384
    if ":" in sig:
        tail = sig.rsplit(":", 1)[-1]
        if tail.isdigit():
            dims = int(tail)
    if coll not in seen:
        out.append((coll, dims))
        seen.add(coll)
    old_style = f"companion_{sig.replace(':', '_')}"
    if old_style not in seen:
        out.append((old_style, dims))
    return out


def _open_dump_mem(llm_conf: Dict[str, Any], collection: str, dims: int):
    cfg = _mem0_config(llm_conf, dims=dims, collection=collection)
    mem = _mem0_from_config(cfg)
    mem.embedding_model = _HashingEmbedder(dims)
    return mem


def _kind_from_meta(meta: Dict[str, Any], fallback: str = "event") -> str:
    kind = str(meta.get("kind") or "").strip()
    if kind in VALID_KINDS:
        return kind
    cats = meta.get("categories") or []
    if isinstance(cats, str):
        cats = [cats]
    if isinstance(cats, list):
        for c in cats:
            mapped = _CAT_TO_KIND.get(str(c).strip().lower())
            if mapped:
                return mapped
    return fallback if fallback in VALID_KINDS else "event"


def _import_dump_to_sqlite(session: Session, dump: List[Dict[str, Any]]) -> int:
    existing = {
        (int(r.character_id), (r.content or "").strip())
        for r in session.exec(select(MemoryFact)).all()
    }
    now = _now()
    n = 0
    for row in dump:
        text = (row.get("text") or "").strip()
        cid = int(row.get("character_id") or 0)
        if not text or not cid or (cid, text) in existing:
            continue
        meta = dict(row.get("meta") or {})
        kind = _kind_from_meta(meta)
        pinned = bool(meta.get("pinned")) or _is_identity_fact(text)
        try:
            importance = float(meta.get("importance") if meta.get("importance") is not None else 0.5)
        except (TypeError, ValueError):
            importance = 0.5
        session.add(MemoryFact(
            character_id=cid,
            kind=kind,
            content=text,
            importance=max(0.0, min(1.0, importance)),
            pinned=pinned,
            created_at=now,
            updated_at=now,
        ))
        existing.add((cid, text))
        n += 1
    if n:
        session.commit()
        print(f"[memory] imported {n} facts into sqlite")
    return n


def _import_legacy_into_sqlite(session: Session, llm_conf: Dict[str, Any]) -> None:
    if _cache.get("imported"):
        return
    try:
        if _IMPORTED.is_file():
            _cache["imported"] = True
            return
    except OSError:
        pass
    ids = _character_ids(session)
    if not ids:
        _cache["imported"] = True
        try:
            MEM0_DIR.mkdir(parents=True, exist_ok=True)
            _IMPORTED.write_text("ok", encoding="utf-8")
        except OSError:
            pass
        return
    dumped = 0
    for coll, dims in _legacy_collections(_read_marker()):
        mem = None
        try:
            mem = _open_dump_mem(llm_conf, coll, dims)
            dump = _dump_collection(mem, ids)
            dumped += _import_dump_to_sqlite(session, dump)
        except Exception as exc:
            print(f"[memory] import {coll} skip: {exc}")
        finally:
            _close_mem(mem)
    _cache["imported"] = True
    try:
        MEM0_DIR.mkdir(parents=True, exist_ok=True)
        _IMPORTED.write_text("ok", encoding="utf-8")
    except OSError:
        pass
    if dumped:
        print(f"[memory] sqlite is now the fact store, imported={dumped}")


def _sqlite_rows(session: Session, character_id: Optional[int] = None) -> List[MemoryFact]:
    stmt = select(MemoryFact)
    if character_id:
        stmt = stmt.where(MemoryFact.character_id == character_id)
    return list(session.exec(
        stmt.order_by(MemoryFact.pinned.desc(), MemoryFact.importance.desc(),
                      MemoryFact.updated_at.desc())
    ).all())


def _wipe_user_vectors(mem, character_ids: Sequence[int]) -> None:
    for cid in character_ids:
        if not cid:
            continue
        for item in _get_all(mem, _uid(cid), top_k=500):
            rid = item.get("id")
            if not rid:
                continue
            try:
                mem.delete(str(rid))
            except Exception:
                pass


def _index_fact(mem, row: MemoryFact) -> None:
    text = (row.content or "").strip()
    if not text or not row.id or not row.character_id:
        return
    mem.add(
        text,
        user_id=_uid(row.character_id),
        infer=False,
        metadata={
            "kind": row.kind if row.kind in VALID_KINDS else "event",
            "pinned": bool(row.pinned),
            "importance": float(row.importance or 0.5),
            "sqlite_id": int(row.id),
            "speaker": row.speaker or "",
            "emotion": row.emotion or "",
            "source": "sqlite",
        },
    )


def _rebuild_from_sqlite(session: Session, mem) -> None:
    ids = _character_ids(session)
    _wipe_user_vectors(mem, ids)
    n = 0
    for row in session.exec(select(MemoryFact)).all():
        try:
            _index_fact(mem, row)
            n += 1
        except Exception as exc:
            print(f"[memory] index skip id={row.id}: {exc}")
    print(f"[memory] rebuilt index from sqlite n={n}")


def _drop_indexed_fact(mem, character_id: int, sqlite_id: int, content: str = "") -> None:
    uid = _uid(character_id)
    for item in _get_all(mem, uid, top_k=200):
        md = _item_meta(item)
        rid = item.get("id")
        if not rid:
            continue
        same_id = str(md.get("sqlite_id") or "") == str(sqlite_id)
        same_text = bool(content) and _item_text(item) == content
        if same_id or same_text:
            try:
                mem.delete(str(rid))
            except Exception:
                pass


def _embedder_choice(session: Session) -> str:
    raw = settings_store.get_all(session).get("memory") or {}
    return embed_svc.normalize_provider(raw.get("embedder"))


def _client(session: Session):
    all_conf = settings_store.get_all(session)
    conf = all_conf.get("llm") or {}
    api_key = (conf.get("api_key") or "").strip()
    choice = _embedder_choice(session)
    from ...locale_pack import current_reply
    llm_key = (api_key, conf.get("base_url") or "", conf.get("model") or "", choice, current_reply())
    with _lock:
        if _cache["mem"] is not None and _cache.get("llm_key") == llm_key:
            return _cache["mem"]
    _import_legacy_into_sqlite(session, conf)
    embedder, note = embed_svc.resolve(conf, choice)
    if note:
        print(f"[memory] {note}")
    if embedder is None:
        embedder = _HashingEmbedder(384)
        semantic = False
        print("[memory] no embedding API and no local MiniLM; facts stay in sqlite, recall uses LLM")
    else:
        semantic = getattr(embedder, "provider", "") != "hashing"
    sig = embed_svc.embed_sig(embedder)
    from ...locale_pack import current_reply
    key = (api_key, conf.get("base_url") or "", conf.get("model") or "", choice, sig, current_reply())
    with _lock:
        if _cache["mem"] is not None and _cache["key"] == key:
            _cache["llm_key"] = llm_key
            return _cache["mem"]
        os.environ["MEM0_TELEMETRY"] = "False"
        os.environ["OPENAI_API_KEY"] = api_key or "local"
        base_url = (conf.get("base_url") or "").rstrip("/")
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url
        _close_mem(_cache.get("mem"))
        _cache["mem"] = None
        try:
            coll = embed_svc.collection_name(sig)
            cfg = _mem0_config(conf, dims=int(embedder.dims), collection=coll)
            mem = _mem0_from_config(cfg)
            mem.embedding_model = embedder
            old = _read_marker()
            if old != sig:
                _rebuild_from_sqlite(session, mem)
                _write_marker(sig)
                print(f"[memory] index {old or 'empty'} -> {sig} collection={coll}")
            _cache["semantic"] = semantic
        except Exception as exc:
            print(f"[memory] mem0 init failed: {exc}")
            return None
        _cache["key"] = key
        _cache["llm_key"] = llm_key
        _cache["mem"] = mem
        _cache["embed_sig"] = sig
        return mem


def reset_client() -> None:
    """设置里换了 embedding / Key 之后，丢掉进程内的旧向量客户端。"""
    with _lock:
        _close_mem(_cache.get("mem"))
        _cache["mem"] = None
        _cache["key"] = None
        _cache["llm_key"] = None
        _cache["embed_sig"] = ""


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
    kind = row.kind if row.kind in VALID_KINDS else "event"
    return {
        "id": str(row.id),
        "character_id": row.character_id,
        "kind": kind,
        "kind_cn": KIND_CN.get(kind, kind),
        "content": row.content,
        "importance": row.importance,
        "pinned": bool(row.pinned),
        "speaker": row.speaker or "",
        "source_message_id": int(row.source_message_id or 0),
        "emotion": row.emotion or "",
        "emotion_intensity": float(row.emotion_intensity or 0),
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


def list_facts(session: Session, character_id: int) -> List[Dict[str, Any]]:
    return [_legacy_to_dict(r) for r in _sqlite_rows(session, character_id)]


def inject_memory(
    session: Session,
    character_id: int,
    messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    query = _last_user_text(messages)
    t0 = time.perf_counter()
    pins = rank.select_message_pins(list_pins(session, character_id))
    picked = _retrieve(session, character_id, query)
    episode = pick_episode(
        session, character_id, query,
        [row.get("id") for row in picked if not row.get("pinned")],
    )
    ms = int((time.perf_counter() - t0) * 1000)
    parts: List[str] = []
    if pins:
        lines = []
        for row in pins:
            text = (row.get("content") or "").strip()
            if not text:
                continue
            mark = "（扮演里钉住的原句）" if row.get("kind") == "rp" else ""
            who = "她" if row.get("role") == "assistant" else "对方"
            lines.append(f"- {who}{mark}：{text}")
        if lines:
            parts.append(
                "钉住的原句（对方要求照原话记得，不参与筛选。问原话时，把冒号后的句子原样说出来，不要改人称）：\n"
                + "\n".join(lines)
            )
    if episode and (episode.get("summary") or "").strip():
        parts.append(
            "一起经历过的一段（只是当时的气氛，话题擦到了才用，不要主动复述）：\n"
            + str(episode.get("summary") or "").strip()[:180]
        )
    fact_lines = []
    seen = set()
    for row in picked:
        text = (row.get("content") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        mark = "（置顶）" if row.get("pinned") else ""
        peak = rank.emotion_peak(str(row.get("emotion") or ""), row.get("emotion_intensity") or 0)
        emo = ""
        if peak > 0 and row.get("kind") in rank.EVENT_KINDS:
            label = _EMO_CN.get(str(row.get("emotion") or ""), str(row.get("emotion") or ""))
            emo = f"（当时{label}）"
        fact_lines.append(f"- [{row.get('kind_cn') or row.get('kind')}]{mark}{emo}{text}")
    if fact_lines:
        parts.append(
            "长期记忆（比刚才几句对话更准；你若刚说过不知道，以这里为准）：\n"
            + "\n".join(fact_lines)
            + "\n对方问起自己是谁、叫什么、以前聊过什么，用这些事实回答，不要让对方再说一遍。"
            "时间词只按事实里写的说。事实没写上周或以前，就不要自己补。昨天不要说成上周。"
            "不要把清单念出来。用户说「历史/记得」时，先当成你们的交往，不是古代史，除非在谈书。"
        )
    if not parts:
        print(f"[memory] inject empty q={query[:40]!r} {ms}ms")
        return messages
    block = "\n\n".join(parts)
    print(
        "[memory] inject pins="
        + str(len(pins))
        + " episode="
        + str(1 if episode else 0)
        + " facts="
        + str(len(fact_lines))
        + f" {ms}ms q="
        + repr(query[:40])
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
    def _line(x: Dict[str, Any]) -> str:
        return (x.get("content") or _item_text(x) or "")[:80]
    numbered = "\n".join(f"{i + 1}. {_line(x)}" for i, x in enumerate(items[:40]))
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


def _hydrate_hits(session: Session, character_id: int, items: List[Dict[str, Any]]) -> List[MemoryFact]:
    rows = _sqlite_rows(session, character_id)
    by_id = {int(r.id): r for r in rows if r.id}
    by_text = {(r.content or "").strip(): r for r in rows}
    out: List[MemoryFact] = []
    seen = set()
    for item in items:
        md = _item_meta(item)
        row = None
        sid = md.get("sqlite_id")
        if str(sid).isdigit():
            row = by_id.get(int(sid))
        if row is None:
            row = by_text.get(_item_text(item))
        if row is None or row.id in seen:
            continue
        seen.add(row.id)
        out.append(row)
    return out


def _hit_vector(item: Dict[str, Any]) -> float:
    for key in ("score", "similarity"):
        if item.get(key) is None:
            continue
        return rank.clamp_vector(item.get(key))
    return 0.5


def _scored_hits(session: Session, character_id: int, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = _hydrate_hits(session, character_id, items)
    by_id = {int(r.id): r for r in rows if r.id}
    by_text = {(r.content or "").strip(): r for r in rows}
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        md = _item_meta(item)
        row = None
        sid = md.get("sqlite_id")
        if str(sid).isdigit():
            row = by_id.get(int(sid))
        if row is None:
            row = by_text.get(_item_text(item))
        if row is None or row.id in seen:
            continue
        score = _hit_vector(item)
        if score < rank.VECTOR_FLOOR:
            continue
        seen.add(row.id)
        fact = _legacy_to_dict(row)
        fact["_vector"] = score
        out.append(fact)
    return out


def _split_scored(pool: List[Dict[str, Any]], now: datetime) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    events: List[Dict[str, Any]] = []
    stable: List[Dict[str, Any]] = []
    for fact in pool:
        kind = str(fact.get("kind") or "event")
        vector = float(fact.get("_vector") or 0)
        if kind in rank.EVENT_KINDS:
            when = _parse_dt(fact.get("created_at"))
            peak = rank.emotion_peak(str(fact.get("emotion") or ""), fact.get("emotion_intensity") or 0)
            fact["_score"] = rank.event_score(
                vector,
                rank.recency_score(when, now),
                peak,
                float(fact.get("importance") or 0.5),
            )
            events.append(fact)
        else:
            fact["_score"] = vector
            stable.append(fact)
    events.sort(key=lambda row: float(row.get("_score") or 0), reverse=True)
    stable.sort(key=lambda row: float(row.get("_score") or 0), reverse=True)
    return events, stable


def _retrieve(session: Session, character_id: int, query: str) -> List[Dict[str, Any]]:
    facts = [_legacy_to_dict(r) for r in _sqlite_rows(session, character_id)]
    if not facts:
        return []
    pinned = [r for r in facts if r.get("pinned")]
    mem = _client(session)
    q = (query or "").strip() or "对方是谁，有什么偏好、约定和还没做完的事"
    conf = settings_store.get_all(session).get("llm") or {}
    pool: List[Dict[str, Any]] = []
    try:
        with _lock:
            if mem is not None and _cache.get("semantic"):
                hits = _search(mem, q, _uid(character_id), top_k=_CANDIDATES)
                pool = _scored_hits(session, character_id, hits)
            elif mem is not None:
                picked = _llm_pick(conf, q, facts, _CANDIDATES)
                for i, fact in enumerate(picked):
                    fact = dict(fact)
                    fact["_vector"] = max(rank.VECTOR_FLOOR, 1.0 - i * 0.03)
                    pool.append(fact)
    except Exception as exc:
        print(f"[memory] retrieve failed: {exc}")
        return rank.assemble_facts(pinned, [], [])
    asked = (query or "").strip()
    if asked:
        pool = [
            fact for fact in pool
            if fact.get("pinned") or rank.relevant_enough(
                float(fact.get("_vector") or 0), asked, fact.get("content") or "",
            )
        ]
    events, stable = _split_scored(pool, _now())
    return rank.assemble_facts(pinned, events, stable)


def scene_hints(session: Session, character_id: int) -> List[str]:
    mem = _client(session)
    if mem is not None:
        try:
            with _lock:
                items = _search(mem, "未完的约定、下次要做的事、最近发生的事", _uid(character_id), top_k=4)
            rows = _hydrate_hits(session, character_id, items)
            texts = [(r.content or "").strip() for r in rows if (r.content or "").strip()]
            if texts:
                return texts[:4]
        except Exception as exc:
            print(f"[memory] scene search failed: {exc}")
    return [
        (r.content or "").strip()
        for r in _sqlite_rows(session, character_id)
        if r.kind == "open_loop" and (r.content or "").strip()
    ][:4]


def retrieve_facts(session: Session, character_id: int, query: str) -> List[Dict[str, Any]]:
    return _retrieve(session, character_id, query)


def strip_perf(text: str) -> str:
    return _PERF_TAG_RE.sub("", text or "").strip()


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _role_labels() -> Tuple[str, str, str]:
    role_user, role_asst = "用户", "助手"
    try:
        from ...locale_pack import prompts
        mem = prompts().get("memory") or {}
        role_user = str(mem.get("role_user") or role_user)
        role_asst = str(mem.get("role_assistant") or role_asst)
    except Exception:
        pass
    sep = ": " if role_user == "User" else "："
    return role_user, role_asst, sep


def _fill_emotion(
    emotion: str,
    intensity: float,
    texts: Sequence[str],
    model_emotion: str = "",
) -> Tuple[str, float]:
    """表演标签优先。没有标签时，用模型给的峰值，再用句子里的生气、伤心。"""
    if rank.emotion_peak(emotion, intensity) > 0:
        return emotion, intensity
    model = (model_emotion or "").strip().lower()
    if model in rank.PEAK_EMOS:
        return model, 0.9
    for text in texts:
        name, level = rank.emotion_from_words(text)
        if name:
            return name, level
    return "", 0.0


def _coerce_extracted(item: Any, window: Optional[Sequence[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """字符串或 {text,kind,n}。序号能对上窗口时，说话人和情绪由代码填。"""
    window = list(window or [])
    index = 0
    if isinstance(item, str):
        text = item.strip()
        kind = "event"
        src = {"speaker": "", "source_message_id": 0, "emotion": "", "emotion_intensity": 0.0}
    elif isinstance(item, dict):
        text = str(item.get("text") or item.get("fact") or item.get("content") or "").strip()
        kind = str(item.get("kind") or "event").strip()
        if kind not in VALID_KINDS:
            kind = "event"
        try:
            index = int(item.get("n") or 0)
        except (TypeError, ValueError):
            index = 0
        if index and window:
            src = rank.attach_source(window, index)
        else:
            try:
                mid = int(item.get("source_message_id") or 0)
            except (TypeError, ValueError):
                mid = 0
            try:
                intensity = float(item.get("emotion_intensity") or 0)
            except (TypeError, ValueError):
                intensity = 0.0
            src = {
                "speaker": str(item.get("speaker") or ""),
                "source_message_id": mid,
                "emotion": str(item.get("emotion") or ""),
                "emotion_intensity": intensity,
            }
    else:
        return None
    if len(text) < 4:
        return None
    if kind not in rank.EVENT_KINDS:
        src["emotion"] = ""
        src["emotion_intensity"] = 0.0
    else:
        near = [text]
        if index and window:
            near.append(str(window[index - 1].get("content") or ""))
            if index < len(window):
                near.append(str(window[index].get("content") or ""))
        model_emo = str(item.get("emotion") or "") if isinstance(item, dict) else ""
        emo, level = _fill_emotion(
            str(src.get("emotion") or ""),
            float(src.get("emotion_intensity") or 0),
            near,
            model_emo,
        )
        src["emotion"] = emo
        src["emotion_intensity"] = level
    speaker = src.get("speaker") or ""
    if speaker not in ("user", "assistant"):
        speaker = ""
    return {
        "text": text[:400],
        "kind": kind,
        "speaker": speaker,
        "source_message_id": int(src.get("source_message_id") or 0),
        "emotion": str(src.get("emotion") or ""),
        "emotion_intensity": float(src.get("emotion_intensity") or 0),
    }


def llm_extract_facts(llm_conf: Dict[str, Any], messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """只打抽取 LLM，不碰向量库。每条事实带回说话人、来源消息和情绪。空结果也合法。"""
    api_key = (llm_conf.get("api_key") or "").strip()
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    window = [m for m in messages if (m.get("content") or "").strip()]
    if not api_key or not base_url or not window:
        return []
    role_user, role_asst, sep = _role_labels()
    lines = []
    for i, m in enumerate(window, start=1):
        role = role_user if m.get("role") == "user" else role_asst
        lines.append(f"{i}. {role}{sep}{(m.get('content') or '').strip()}")
    blob = "\n".join(lines)[:8000]
    if not blob.strip():
        return []
    payload = {
        "model": llm_conf.get("model") or "qwen-plus",
        "temperature": 0.1,
        "stream": False,
        "messages": [
            {"role": "system", "content": _extract_hint() + _extract_tail()},
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
        out: List[Dict[str, Any]] = []
        seen = set()
        user_blob = "\n".join(
            str(m.get("content") or "") for m in window if m.get("role") == "user"
        )
        for item in facts:
            spec = _coerce_extracted(item, window)
            if spec is None or spec["text"] in seen:
                continue
            if not rank.allow_extracted(spec["text"], spec["kind"], user_blob):
                continue
            if spec["kind"] == "open_loop" and not spec.get("source_message_id"):
                continue
            seen.add(spec["text"])
            out.append(spec)
        return out
    except Exception as exc:
        print(f"[memory] extract llm failed: {exc}")
        return []


def llm_episode_summary(
    llm_conf: Dict[str, Any],
    messages: List[Dict[str, Any]],
    fact_lines: Sequence[str],
) -> str:
    """跟抽取同一次任务写摘要，不在回复的关键路径上。失败就当没有这段经历。"""
    api_key = (llm_conf.get("api_key") or "").strip()
    base_url = (llm_conf.get("base_url") or "").rstrip("/")
    if not api_key or not base_url or not messages:
        return ""
    role_user, role_asst, sep = _role_labels()
    lines = []
    for m in messages:
        role = role_user if m.get("role") == "user" else role_asst
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{role}{sep}{content}")
    noted = "\n".join(f"- {line}" for line in fact_lines if line)
    blob = "\n".join(lines)[:6000]
    if noted:
        blob += "\n\n刚记下的事实：\n" + noted
    payload = {
        "model": llm_conf.get("model") or "qwen-plus",
        "temperature": 0.2,
        "stream": False,
        "messages": [
            {"role": "system", "content": _episode_hint()},
            {"role": "user", "content": blob},
        ],
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(45, connect=8), trust_env=False) as client:
            resp = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        if resp.status_code != 200:
            print(f"[memory] episode llm HTTP {resp.status_code}")
            return ""
        text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        data = _parse_json_blob(text) or {}
        summary = str((data.get("summary") if isinstance(data, dict) else "") or "").strip()
        if len(summary) < 4:
            return ""
        return summary[:400]
    except Exception as exc:
        print(f"[memory] episode llm failed: {exc}")
        return ""


def _sync_index(session: Session, row: MemoryFact, *, old_content: str = "") -> None:
    if not row.id or not row.character_id:
        return
    try:
        mem = _client(session)
    except Exception:
        return
    if mem is None:
        return
    try:
        _drop_indexed_fact(mem, int(row.character_id), int(row.id), old_content)
        _index_fact(mem, row)
    except Exception as exc:
        print(f"[memory] index sync skip id={row.id}: {exc}")


def store_extracted_facts(session: Session, character_id: int, facts: Sequence[Any]) -> List[int]:
    ids: List[int] = []
    with _lock:
        have = {
            (r.content or "").strip()
            for r in session.exec(
                select(MemoryFact).where(MemoryFact.character_id == character_id)
            ).all()
        }
        for fact in facts:
            spec = _coerce_extracted(fact)
            if spec is None or spec["text"] in have:
                continue
            if not rank.allow_extracted(spec["text"], spec["kind"]):
                continue
            if any(rank.same_memory(spec["text"], old) for old in have):
                continue
            identity = _is_identity_fact(spec["text"])
            kind = "person" if identity else spec["kind"]
            emotion = ""
            intensity = 0.0
            peak = 0.0
            if kind in rank.EVENT_KINDS:
                emotion = spec["emotion"]
                intensity = float(spec["emotion_intensity"] or 0)
                peak = rank.emotion_peak(emotion, intensity)
            importance = rank.importance_for(kind, peak, identity)
            out = _write_fact(
                session, character_id, fact_id=None,
                kind=kind, content=spec["text"], importance=importance,
                pinned=True if identity else False,
            )
            have.add(spec["text"])
            row = session.get(MemoryFact, int(out["id"])) if out.get("id") else None
            if row is None:
                continue
            row.speaker = spec["speaker"]
            row.source_message_id = int(spec["source_message_id"] or 0)
            row.emotion = emotion
            row.emotion_intensity = intensity
            session.add(row)
            session.commit()
            session.refresh(row)
            _sync_index(session, row)
            if row.id:
                ids.append(int(row.id))
    return ids


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
    with _lock:
        old_content = ""
        if fact_id and str(fact_id).isdigit():
            prev = session.get(MemoryFact, int(fact_id))
            if prev and prev.character_id == character_id:
                old_content = prev.content or ""
            elif prev is None:
                raise KeyError("fact not found")
        elif fact_id:
            raise KeyError("fact not found")
        out = _write_fact(
            session, character_id, fact_id=fact_id, kind=kind,
            content=content, importance=importance, pinned=pinned,
        )
        row = session.get(MemoryFact, int(out["id"])) if out.get("id") else None
        if row is not None:
            _sync_index(session, row, old_content=old_content)
        return out


def _write_fact(session: Session, character_id: int, *,
                fact_id: Optional[str], kind: str, content: str,
                importance: float, pinned: Optional[bool]) -> Dict[str, Any]:
    now = _now()
    row: Optional[MemoryFact] = None
    if fact_id and str(fact_id).isdigit():
        row = session.get(MemoryFact, int(fact_id))
        if row and row.character_id != character_id:
            row = None
        if fact_id and row is None:
            raise KeyError("fact not found")
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
    with _lock:
        if str(fact_id).isdigit():
            row = session.get(MemoryFact, int(fact_id))
            if not row or row.character_id != character_id:
                return False
            content = row.content or ""
            sid = int(row.id)
            session.delete(row)
            session.commit()
            mem = _cache.get("mem")
            if mem is None:
                try:
                    mem = _client(session)
                except Exception:
                    mem = None
            if mem is not None:
                try:
                    _drop_indexed_fact(mem, character_id, sid, content)
                except Exception as exc:
                    print(f"[memory] index delete skip: {exc}")
            return True
        mem = _cache.get("mem")
        if mem is None:
            try:
                mem = _client(session)
            except Exception:
                mem = None
        if mem is None:
            return False
        try:
            mem.delete(str(fact_id))
            return True
        except Exception:
            return False


def _pin_dict(row: PinnedMessage) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "character_id": row.character_id,
        "message_id": int(row.message_id or 0),
        "role": row.role or "",
        "content": row.content or "",
        "kind": row.kind or "qa",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def list_pins(session: Session, character_id: int) -> List[Dict[str, Any]]:
    rows = session.exec(
        select(PinnedMessage)
        .where(PinnedMessage.character_id == character_id)
        .order_by(PinnedMessage.id)
    ).all()
    return [_pin_dict(row) for row in rows]


def pin_message(session: Session, character_id: int, message_id: int) -> Dict[str, Any]:
    msg = session.get(ChatMessage, int(message_id))
    if msg is None or int(msg.character_id) != int(character_id):
        raise KeyError("message not found")
    raw = (msg.content or "").strip() or (msg.full_content or "").strip()
    text = strip_perf(raw)
    if not text:
        raise ValueError("empty message")
    existing = session.exec(
        select(PinnedMessage).where(
            PinnedMessage.character_id == character_id,
            PinnedMessage.message_id == int(message_id),
        )
    ).first()
    if existing is not None:
        return _pin_dict(existing)
    row = PinnedMessage(
        character_id=int(character_id),
        message_id=int(message_id),
        role=msg.role or "",
        content=text[:800],
        kind=msg.kind or "qa",
        created_at=_now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _pin_dict(row)


def delete_pin(session: Session, character_id: int, pin_id: str) -> bool:
    if not str(pin_id).isdigit():
        return False
    row = session.get(PinnedMessage, int(pin_id))
    if row is None or int(row.character_id) != int(character_id):
        return False
    session.delete(row)
    session.commit()
    return True


def _episode_dict(row: MemoryEpisode) -> Dict[str, Any]:
    raw = row.key_events or "[]"
    try:
        keys = json.loads(raw)
    except (TypeError, ValueError):
        keys = []
    if not isinstance(keys, list):
        keys = []
    return {
        "id": str(row.id),
        "character_id": row.character_id,
        "summary": row.summary or "",
        "key_events": [int(x) for x in keys if str(x).isdigit()],
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def list_episodes(session: Session, character_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    rows = session.exec(
        select(MemoryEpisode)
        .where(MemoryEpisode.character_id == character_id)
        .order_by(MemoryEpisode.id.desc())
    ).all()
    return [_episode_dict(row) for row in rows[:limit]]


def save_episode(
    session: Session,
    character_id: int,
    summary: str,
    fact_ids: Sequence[int],
) -> Dict[str, Any]:
    text = (summary or "").strip()
    if len(text) < 4:
        raise ValueError("summary required")
    row = MemoryEpisode(
        character_id=int(character_id),
        summary=text[:400],
        key_events=json.dumps([int(i) for i in fact_ids if i]),
        created_at=_now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _episode_dict(row)


def delete_episode(session: Session, character_id: int, episode_id: str) -> bool:
    if not str(episode_id).isdigit():
        return False
    row = session.get(MemoryEpisode, int(episode_id))
    if row is None or int(row.character_id) != int(character_id):
        return False
    session.delete(row)
    session.commit()
    return True


def pick_episode(
    session: Session,
    character_id: int,
    query: str,
    fact_ids: Optional[Sequence[Any]] = None,
) -> Optional[Dict[str, Any]]:
    rows = list_episodes(session, character_id, limit=30)
    return rank.pick_episode_row(rows, query, fact_ids)


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
