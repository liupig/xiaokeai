import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse

from app import locale_pack
from app.routers import speech
from app.services import cloud_key, settings_store, tts, tts_cosy


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_cosy_engine_streams_pcm(monkeypatch):
    """The CosyVoice branch used an undefined `cancel`, so every request failed with NameError."""
    monkeypatch.setattr(
        settings_store, "get_all", lambda session: {"tts": {"engine": "cosy"}, "llm": {}}
    )
    monkeypatch.setattr(settings_store, "apply_llm_overlay", lambda llm: llm)
    monkeypatch.setattr(tts, "resolve_voice", lambda engine, voice, saved="": "voice-1")
    monkeypatch.setattr(locale_pack, "align_voice", lambda engine, voice, lang: voice)
    monkeypatch.setattr(cloud_key, "ali_key", lambda llm: "sk-test")

    async def fake_synthesize_pcm(text, voice, api_key):
        assert (text, voice, api_key) == ("你好", "voice-1", "sk-test")
        yield b"first"
        yield b"second"

    monkeypatch.setattr(tts_cosy, "synthesize_pcm", fake_synthesize_pcm)

    async def receive():
        await asyncio.Future()

    response = await speech.tts_endpoint(
        speech.TTSRequest(text="你好"),
        Request({"type": "http"}, receive),
        MagicMock(),
    )

    assert isinstance(response, StreamingResponse)
    assert response.headers["X-Audio-Format"] == "pcm_s16le"
    assert [chunk async for chunk in response.body_iterator] == [b"first", b"second"]
