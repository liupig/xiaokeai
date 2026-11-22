import asyncio
import queue
import threading

import pytest
from fastapi import HTTPException, Request

from app.routers.speech import _first_local_audio
from app.services import tts_qwen


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_disconnect_before_first_pcm_cancels_the_worker_job(monkeypatch):
    commands = queue.Queue()
    monkeypatch.setattr(tts_qwen, "_ensure_worker", lambda: None)
    monkeypatch.setattr(tts_qwen, "_in_q", commands)
    monkeypatch.setattr(tts_qwen, "_worker_alive", lambda: True)
    cancel = threading.Event()
    agen = tts_qwen.synthesize_pcm("旧句", "Serena", cancel=cancel)

    async def receive():
        while commands.empty():
            await asyncio.sleep(0)
        return {"type": "http.disconnect"}

    with pytest.raises(HTTPException) as err:
        await _first_local_audio(Request({"type": "http"}, receive), agen, cancel)
    assert err.value.status_code == 499
    assert cancel.is_set()
    synth = commands.get_nowait()
    assert synth[0] == "synth"
    assert commands.get_nowait() == ("cancel", synth[1])
    assert commands.empty()
    assert synth[1] not in tts_qwen._waiters


@pytest.mark.anyio
async def test_first_pcm_hands_off_to_normal_stream():
    cancel = threading.Event()

    async def receive():
        await asyncio.Future()

    async def chunks():
        yield b"first"
        yield b"next"

    agen = chunks()
    assert await _first_local_audio(Request({"type": "http"}, receive), agen, cancel) == b"first"
    assert [chunk async for chunk in agen] == [b"next"]
    assert not cancel.is_set()
