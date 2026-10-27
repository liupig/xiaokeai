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
    assert patch["stt"]["engine"] == "volc"
    assert patch["tts"]["engine"] == "volc"
    assert patch["tts"]["voice"] == default_voice("volc", "zh-CN")
    assert patch["memory"]["embedder"] == "auto"
    assert patch["modules"]["memory"] is True
    assert patch["hardware"]["auto"] is False
    assert patch["hardware"]["tier"] == "online"
    assert patch["hardware"]["reason"] == ONLINE_REASON


def test_online_pack_ignores_sibling_content():
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        tmp_path = Path(raw)
        online = tmp_path / "xiaoke-ai-online"
        sibling = tmp_path / "xiaoke-ai-B"
        (online / "assets" / "models").mkdir(parents=True)
        (online / ONLINE_MARKER).write_text("{}\n", encoding="utf-8")
        sibling.mkdir()
        (sibling / "xiaoke-content.json").write_text("{}\n", encoding="utf-8")
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
    assert rec["stt_engine"] == "volc"
    assert rec["tts_engine"] == "volc"
    assert rec["memory"] is True
    assert rec["tier"] == "online"
    assert "本地" not in rec["reason"]
