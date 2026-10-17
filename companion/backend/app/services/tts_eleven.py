"""ElevenLabs 朗读：Flash v2.5，官方预置音色，流式 mp3。

只收默认音色和经典预置音色（Rachel、Adam 等），不含用户自己克隆的库。
官方说明这些 Default voices 到 2026-12-31 之后会停用。
"""
from __future__ import annotations

from typing import AsyncIterator, Dict, List
from urllib.parse import quote

import httpx

ELEVEN_TTS_MODEL = "eleven_flash_v2_5"
SAMPLE_RATE = 44100

ELEVEN_VOICES: List[Dict[str, str]] = [
    {"id": "21m00Tcm4TlvDq8ikWAM", "label": "Rachel（沉稳女声）"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "label": "Sarah（柔和女声）"},
    {"id": "9BWtsMINqrJLrRacOk9x", "label": "Aria（美式女声）"},
    {"id": "FGY2WhTYpPnrIDTdsKH5", "label": "Laura（美式女声）"},
    {"id": "Xb7hH8MSUJpSbSDYk0k2", "label": "Alice（英伦女声）"},
    {"id": "XrExE9yKIg1WjnnlVkGX", "label": "Matilda（温暖女声）"},
    {"id": "cgSgspJ2msm6clMCkdW9", "label": "Jessica（美式女声）"},
    {"id": "pFZP5JQG7iQjIQuC4Bku", "label": "Lily（英伦女声）"},
    {"id": "AZnzlk1XvdvUeBnXmlld", "label": "Domi（自信女声）"},
    {"id": "MF3mGyEYCl7XYWbV9V6O", "label": "Elli（轻快女声）"},
    {"id": "LcfcDJNUP1GQjkzn1xUU", "label": "Emily（冷静女声）"},
    {"id": "XB0fDUnXU5powFXDhCwa", "label": "Charlotte（女声）"},
    {"id": "ThT5KcBeYPX3keUQqHPh", "label": "Dorothy（亲切女声）"},
    {"id": "jsCqWAovK2LkecY7zXl4", "label": "Freya（女声）"},
    {"id": "jBpfuIE2acCO8z3wKNLl", "label": "Gigi（女声）"},
    {"id": "oWAxZDx7w5VEj9dCyTzz", "label": "Grace（女声）"},
    {"id": "piTKgcLEGmPE4e6mEKli", "label": "Nicole（耳语女声）"},
    {"id": "pMsXgVXv3BLzUgSXRplE", "label": "Serena（亲切女声）"},
    {"id": "z9fAnlkpzviPz146aGWa", "label": "Glinda（女声）"},
    {"id": "zrHiDhphv9ZnVXBqCLjz", "label": "Mimi（女声）"},
    {"id": "pNInz6obpgDQGcFmaJgB", "label": "Adam（深沉男声）"},
    {"id": "ErXwobaYiN019PkySvjV", "label": "Antoni（沉稳男声）"},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "label": "Josh（年轻男声）"},
    {"id": "VR6AewLTigWG4xSOukaG", "label": "Arnold（沙哑男声）"},
    {"id": "yoZ06aMxZJJ28mfd3POQ", "label": "Sam（叙述男声）"},
    {"id": "CwhRBWXzGAHq8TQ4Fs17", "label": "Roger（美式男声）"},
    {"id": "IKne3meq5aSn9XLyUdCD", "label": "Charlie（澳洲男声）"},
    {"id": "JBFqnCBsd6RMkjVDRZzb", "label": "George（英伦男声）"},
    {"id": "N2lVS1w4EtoT3dr4eOWO", "label": "Callum（男声）"},
    {"id": "SOYHLrjzK2X1ezoPC6cr", "label": "Harry（英伦男声）"},
    {"id": "TX3LPaxmHKxFdv7VOQHJ", "label": "Liam（青年男声）"},
    {"id": "bIHbv24MWmeRgasZH58o", "label": "Will（美式男声）"},
    {"id": "cjVigY5qzO86Huf0OWal", "label": "Eric（美式男声）"},
    {"id": "iP95p4xoKVk53GoZ742B", "label": "Chris（随和男声）"},
    {"id": "nPczCjzI2devNBz1zQrb", "label": "Brian（深沉男声）"},
    {"id": "onwK4e9ZLuTAKqWW03F9", "label": "Daniel（英伦男声）"},
    {"id": "pqHfZKP75CvOlQylNhV4", "label": "Bill（男声）"},
    {"id": "SAz9YHcvj6GT2YYXdXww", "label": "River（中性）"},
    {"id": "29vD33N1CtxCmqQRPOHJ", "label": "Drew（男声）"},
    {"id": "2EiwWnXFnvU5JabPnv8n", "label": "Clyde（男声）"},
    {"id": "5Q0t7uMcjvnagumLfvZi", "label": "Paul（男声）"},
    {"id": "CYw3kZ02Hs0563khs1Fj", "label": "Dave（英伦男声）"},
    {"id": "D38z5RcWu1voky8WS1ja", "label": "Fin（男声）"},
    {"id": "GBv7mTt0atIp3Br8iCZE", "label": "Thomas（男声）"},
    {"id": "ODq5zmih8GrVes37Dizd", "label": "Patrick（男声）"},
    {"id": "ZQe5CZNOzWyzPSCn5a3c", "label": "James（男声）"},
    {"id": "Zlb1dXrM653N07WRdFW3", "label": "Joseph（男声）"},
    {"id": "bVMeCyTHy58xNoL34h3p", "label": "Jeremy（男声）"},
    {"id": "flq6f7yk4E4fJM5XTYuZ", "label": "Michael（男声）"},
    {"id": "g5CIjZEefAph4nQFvHAz", "label": "Ethan（男声）"},
    {"id": "t0jbNlBVZ17f02VDIeMI", "label": "Jessie（男声）"},
    {"id": "zcAOhNBS3c14rBihAFp1", "label": "Giovanni（男声）"},
]


def list_voices() -> List[Dict[str, str]]:
    return [{**v, "engine": "eleven"} for v in ELEVEN_VOICES]


def voice_ids() -> set:
    return {v["id"] for v in ELEVEN_VOICES}


def request_body(text: str) -> Dict[str, str]:
    return {"text": text, "model_id": ELEVEN_TTS_MODEL}


def speech_url(voice: str) -> str:
    return (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        f"{quote(voice, safe='')}/stream?output_format=mp3_44100_128"
    )


async def synthesize_mp3(text: str, voice: str, api_key: str) -> AsyncIterator[bytes]:
    if not api_key:
        raise RuntimeError("ElevenLabs 合成需要 API Key。请设置环境变量 ELEVENLABS_API_KEY。")
    if voice not in voice_ids():
        raise ValueError(f"音色「{voice}」不在 ElevenLabs 预置列表里")
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=8), trust_env=False) as client:
        async with client.stream(
            "POST",
            speech_url(voice),
            headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
            json=request_body(text),
        ) as resp:
            if resp.status_code != 200:
                raw = await resp.aread()
                detail = raw.decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"ElevenLabs 合成失败 HTTP {resp.status_code}：{detail}")
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk
