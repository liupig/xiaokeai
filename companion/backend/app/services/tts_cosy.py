"""在线流式 TTS：百炼 CosyVoice-v3-Flash（WebSocket 回调吐 PCM）。"""
from __future__ import annotations

import asyncio
import threading
from typing import AsyncIterator, Dict, List

COSY_VOICES = [
    {"id": "longanhuan", "label": "龙安欢（欢脱元气女）"},
    {"id": "longanyang", "label": "龙安洋（阳光大男孩）"},
    {"id": "longanling_v3", "label": "龙安灵（思维灵动女）"},
    {"id": "longanya_v3", "label": "龙安雅（高雅气质女）"},
    {"id": "longanwen_v3", "label": "龙安温（优雅知性女）"},
    {"id": "longanqin_v3", "label": "龙安亲（亲和活泼女）"},
    {"id": "longanyun_v3", "label": "龙安昀（居家暖男）"},
    {"id": "longanzhi_v3", "label": "龙安智（睿智轻熟男）"},
]

SAMPLE_RATE = 24000
MODEL = "cosyvoice-v3-flash"


def voice_ids() -> set:
    return {v["id"] for v in COSY_VOICES}


def list_voices() -> List[Dict[str, str]]:
    return [{**v, "engine": "cosy"} for v in COSY_VOICES]


async def synthesize_pcm(text: str, voice: str, api_key: str) -> AsyncIterator[bytes]:
    """边合成边产出 24kHz / 16bit / mono PCM。"""
    if not api_key.strip():
        raise RuntimeError("未配置百炼 API Key，请在设置 → AI 对话里填写")
    if voice not in voice_ids():
        raise ValueError(f"音色「{voice}」不被 CosyVoice 支持")

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def put(item) -> None:
        loop.call_soon_threadsafe(q.put_nowait, item)

    def worker() -> None:
        try:
            import dashscope
            from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

            class CB(ResultCallback):
                def on_data(self, data: bytes) -> None:
                    if data:
                        put(("data", data))

                def on_complete(self) -> None:
                    put(("done", b""))

                def on_error(self, message: str) -> None:
                    put(("error", str(message)))

            dashscope.api_key = api_key
            syn = SpeechSynthesizer(
                model=MODEL,
                voice=voice,
                format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                callback=CB(),
            )
            syn.call(text)
            put(("done", b""))
        except Exception as exc:
            put(("error", str(exc)))

    threading.Thread(target=worker, daemon=True, name="cosy-tts").start()
    finished = False
    while not finished:
        kind, payload = await q.get()
        if kind == "data":
            yield payload
        elif kind == "error":
            raise RuntimeError(payload)
        else:
            finished = True
