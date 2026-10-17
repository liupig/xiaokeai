"""OpenAI 朗读：gpt-4o-mini-tts，官方 13 个预置音色，返回 mp3。

音色按官方 Text to speech 指南。marin、cedar 是官方推荐的两把。
"""
from __future__ import annotations

from typing import AsyncIterator, Dict, List

import httpx

OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
SAMPLE_RATE = 24000

OPENAI_VOICES: List[Dict[str, str]] = [
    {"id": "marin", "label": "Marin（官方推荐）"},
    {"id": "cedar", "label": "Cedar（官方推荐）"},
    {"id": "alloy", "label": "Alloy"},
    {"id": "ash", "label": "Ash"},
    {"id": "ballad", "label": "Ballad"},
    {"id": "coral", "label": "Coral"},
    {"id": "echo", "label": "Echo"},
    {"id": "fable", "label": "Fable"},
    {"id": "nova", "label": "Nova"},
    {"id": "onyx", "label": "Onyx"},
    {"id": "sage", "label": "Sage"},
    {"id": "shimmer", "label": "Shimmer"},
    {"id": "verse", "label": "Verse"},
]


def list_voices() -> List[Dict[str, str]]:
    return [{**v, "engine": "openai"} for v in OPENAI_VOICES]


def voice_ids() -> set:
    return {v["id"] for v in OPENAI_VOICES}


def request_body(text: str, voice: str) -> Dict[str, str]:
    return {
        "model": OPENAI_TTS_MODEL,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
    }


async def synthesize_mp3(text: str, voice: str, api_key: str) -> AsyncIterator[bytes]:
    if not api_key:
        raise RuntimeError(
            "OpenAI 合成需要 API Key。在设置 → AI 对话里选 OpenAI 并填写，或设置环境变量 OPENAI_API_KEY。"
        )
    if voice not in voice_ids():
        raise ValueError(f"音色「{voice}」不在 OpenAI 预置列表里")
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=8), trust_env=False) as client:
        async with client.stream(
            "POST",
            OPENAI_TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=request_body(text, voice),
        ) as resp:
            if resp.status_code != 200:
                raw = await resp.aread()
                detail = raw.decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"OpenAI 合成失败 HTTP {resp.status_code}：{detail}")
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk
