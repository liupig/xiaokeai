"""在线包默认引擎：不联网，只核对预写配置。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.locale_pack import default_voice  # noqa: E402
from app.paths import ONLINE_MARKER, resolve_content_root  # noqa: E402
from app.services.autotune import ONLINE_REASON, online_settings_patch, recommend_online  # noqa: E402


def test_online_patch_uses_cloud_speech_and_keeps_memory():
    patch = online_settings_patch()
    assert patch["stt"]["engine"] == "browser"
    assert patch["tts"]["engine"] == "edge"
    assert patch["tts"]["voice"] == default_voice("edge", "zh-CN")
    assert patch["memory"]["embedder"] == "doubao"
    assert patch["modules"]["memory"] is True
    assert patch["modules"]["glance"] is False
    assert patch["modules"]["sight"] is False
    assert patch["hardware"]["auto"] is False
    assert patch["hardware"]["tier"] == "online"
    assert patch["hardware"]["reason"] == ONLINE_REASON


def test_online_pack_ignores_sibling_content(monkeypatch):
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        tmp_path = Path(raw)
        online = tmp_path / "xiaoke-ai-online"
        sibling = tmp_path / "xiaoke-ai-B"
        (online / "assets" / "models").mkdir(parents=True)
        (online / ONLINE_MARKER).write_text("{}\n", encoding="utf-8")
        sibling.mkdir()
        (sibling / "xiaoke-content.json").write_text("{}\n", encoding="utf-8")
        monkeypatch.setenv("COMPANION_CONTENT", str(sibling))
        assert resolve_content_root(online) == online.resolve()


def test_agent_pack_pairs_same_stamp():
    import os
    import tempfile

    old = os.environ.pop("COMPANION_CONTENT", None)
    try:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            a = tmp / "xiaoke-ai-agent-A-20261027120000"
            b = tmp / "xiaoke-ai-agent-B-20261027120000"
            older = tmp / "xiaoke-ai-agent-B-20261001000000"
            a.mkdir()
            b.mkdir()
            older.mkdir()
            (b / "xiaoke-content.json").write_text("{}\n", encoding="utf-8")
            (older / "xiaoke-content.json").write_text("{}\n", encoding="utf-8")
            assert resolve_content_root(a) == b.resolve()
    finally:
        if old is not None:
            os.environ["COMPANION_CONTENT"] = old


def test_online_recommend_does_not_require_local_weights():
    rec = recommend_online({
        "ram_gb": 32,
        "vram_gb": 24,
        "cores": 16,
        "fingerprint": "test",
    })
    assert rec["stt_engine"] == "browser"
    assert rec["tts_engine"] == "edge"
    assert rec["memory"] is True
    assert rec["tier"] == "online"
    assert "本地" not in rec["reason"]


def test_online_requirements_have_no_inference_or_vision_dependencies():
    backend = Path(__file__).resolve().parents[1]
    online = (backend / "requirements-online.txt").read_text(encoding="utf-8").lower()
    for package in (
        "torch", "sherpa-onnx", "qwen-tts", "qwen3-tts-streaming", "transformers",
        "onnxruntime", "fastembed", "rapidocr", "opencv", "scipy", "librosa",
    ):
        assert package not in online
    for package in ("fastapi", "httpx", "mem0ai", "numpy", "websockets"):
        assert package in online
    assert "sqlalchemy==2.0.52" in online
    assert "sqlmodel==0.0.39" in online
    offline = (backend / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "sherpa-onnx" in offline
    assert "qwen-tts" in offline
    assert "fastembed" in offline
    assert "rapidocr" in offline


def test_online_embedding_never_falls_back_to_local(monkeypatch):
    from app.modules.memory import embedder

    monkeypatch.setattr(embedder, "_online_pack", lambda: True)
    monkeypatch.setattr(embedder.RemoteEmbedder, "connect", lambda *args: None)
    monkeypatch.setattr(
        embedder, "probe_local_minilm",
        lambda: (_ for _ in ()).throw(AssertionError("online pack tried local MiniLM")),
    )
    found, note = embedder.resolve({"api_key": "test", "base_url": embedder.DOUBAO_BASE}, "doubao")
    assert found is None
    assert "不回退本地模型" in note


def test_offline_embedding_fallback_is_unchanged(monkeypatch):
    from app.modules.memory import embedder

    from types import SimpleNamespace
    local = SimpleNamespace(provider="local", model_name="minilm")
    monkeypatch.setattr(embedder, "_online_pack", lambda: False)
    monkeypatch.setattr(embedder.RemoteEmbedder, "connect", lambda *args: None)
    monkeypatch.setattr(embedder, "probe_local_minilm", lambda: local)
    found, _ = embedder.resolve({"api_key": "test", "base_url": embedder.DOUBAO_BASE}, "doubao")
    assert found is local
