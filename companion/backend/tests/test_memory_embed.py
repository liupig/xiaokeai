"""记忆：SQLite 是事实真相源；embedding 按 collection 隔离。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.memory import embedder as embed_svc  # noqa: E402


class _FakeEmb:
    def __init__(self, provider: str, model: str, dims: int):
        self.provider = provider
        self.model_name = model
        self.model = model
        self.dims = dims


def test_guess_provider() -> None:
    assert embed_svc.guess_provider({
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key": "uuid-key",
    }) == "doubao"
    assert embed_svc.guess_provider({
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-abc",
    }) == "qwen"
    assert embed_svc.guess_provider({
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-deepseek",
    }) == "local"
    assert embed_svc.guess_provider({
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-openai",
    }) == "openai"
    assert embed_svc.guess_provider({
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key": "AIza",
    }) == "gemini"
    assert embed_svc.guess_provider({
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "sk-or",
    }) == "local"


def test_collection_isolation() -> None:
    doubao = _FakeEmb("doubao", "doubao-embedding-large", 2048)
    qwen = _FakeEmb("qwen", "text-embedding-v3", 1024)
    local = _FakeEmb("local", "minilm", 384)
    s1 = embed_svc.embed_sig(doubao)
    s2 = embed_svc.embed_sig(qwen)
    s3 = embed_svc.embed_sig(local)
    assert s1 != s2 != s3
    names = {embed_svc.collection_name(s) for s in (s1, s2, s3)}
    assert len(names) == 3
    assert embed_svc.collection_name(s1).startswith("companion_")


def test_credentials_do_not_cross_vendors() -> None:
    volc = {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key": "volc-key",
    }
    qwen = {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-qwen",
    }
    saved = {k: os.environ.pop(k, None) for k in (
        "ARK_API_KEY", "VOLC_ARK_API_KEY", "DASHSCOPE_API_KEY",
    )}
    try:
        d_key, d_base = embed_svc.doubao_credentials(volc)
        assert d_key == "volc-key"
        assert "volces.com" in d_base
        assert embed_svc.qwen_credentials(volc) == ("", "")
        q_key, q_base = embed_svc.qwen_credentials(qwen)
        assert q_key == "sk-qwen"
        assert "dashscope" in q_base
        assert embed_svc.doubao_credentials(qwen) == ("", "")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_sqlite_survives_embedder_switch(tmp_path: Path) -> None:
    from sqlmodel import Session, SQLModel, create_engine

    from app.models import MemoryFact
    from app.modules.memory import service

    db = tmp_path / "mem.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    indexed: Dict[str, List[str]] = {}

    class _Mem:
        def __init__(self, coll: str):
            self.coll = coll
            indexed.setdefault(coll, [])

        def add(self, text, user_id=None, infer=False, metadata=None):
            indexed[self.coll].append(text)
            return {"results": [{"id": "v", "memory": text, "metadata": metadata or {}}]}

        def get_all(self, **kwargs):
            return {"results": []}

        def search(self, *args, **kwargs):
            return {"results": []}

        def delete(self, *args, **kwargs):
            return True

    current = {"mem": None}

    def fake_client(session):
        return current["mem"]

    orig = service._client
    service._client = fake_client  # type: ignore[method-assign]
    try:
        with Session(engine) as session:
            service.upsert_fact(session, 1, kind="person", content="用户的名字是阿星", pinned=True)
            service.upsert_fact(session, 1, kind="preference", content="喜欢听雨")
            before = service.list_facts(session, 1)
            assert [r["content"] for r in before] == ["用户的名字是阿星", "喜欢听雨"]

            current["mem"] = _Mem("companion_qwen_text_embedding_v3_1024")
            service.store_extracted_facts(session, 1, ["喜欢听雨", "养了一只猫"])
            mid = service.list_facts(session, 1)
            texts = [r["content"] for r in mid]
            assert "用户的名字是阿星" in texts
            assert "喜欢听雨" in texts
            assert "养了一只猫" in texts
            assert texts.count("喜欢听雨") == 1

            current["mem"] = _Mem("companion_doubao_doubao_embedding_large_2048")
            after = service.list_facts(session, 1)
            assert {r["content"] for r in after} == set(texts)
            assert after[0]["id"].isdigit()
    finally:
        service._client = orig  # type: ignore[method-assign]
        engine.dispose()


def test_normalize_provider() -> None:
    assert embed_svc.normalize_provider("Qwen") == "qwen"
    assert embed_svc.normalize_provider("nope") == "auto"
    assert embed_svc.normalize_provider(None) == "auto"


if __name__ == "__main__":
    import tempfile

    test_guess_provider()
    test_collection_isolation()
    test_credentials_do_not_cross_vendors()
    test_normalize_provider()
    with tempfile.TemporaryDirectory() as d:
        test_sqlite_survives_embedder_switch(Path(d))
    print("ok")
