"""Gemini 朗读：gemini-3.8-flash-lite-tts，官方 30 个预置音色。

流式接口吐 24kHz 16-bit 单声道 PCM，和本地合成同一条播放路径。
"""
from __future__ import annotations

import base64
import json
from typing import AsyncIterator, Dict, List

import httpx

GEMINI_TTS_MODEL = "gemini-3.8-flash-lite-tts"
GEMINI_TTS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_TTS_MODEL}:streamGenerateContent?alt=sse"
)
SAMPLE_RATE = 24000

GEMINI_VOICES: List[Dict[str, str]] = [
    {"id": "Kore", "label": "Kore（坚定女声）"},
    {"id": "Zephyr", "label": "Zephyr（明快女声）"},
    {"id": "Leda", "label": "Leda（年轻女声）"},
    {"id": "Aoede", "label": "Aoede（清爽女声）"},
    {"id": "Callirrhoe", "label": "Callirrhoe（随和女声）"},
    {"id": "Autonoe", "label": "Autonoe（明亮女声）"},
    {"id": "Despina", "label": "Despina（顺滑女声）"},
    {"id": "Erinome", "label": "Erinome（清晰女声）"},
    {"id": "Laomedeia", "label": "Laomedeia（上扬女声）"},
    {"id": "Achernar", "label": "Achernar（轻柔女声）"},
    {"id": "Gacrux", "label": "Gacrux（成熟女声）"},
    {"id": "Pulcherrima", "label": "Pulcherrima（女声）"},
    {"id": "Vindemiatrix", "label": "Vindemiatrix（温柔女声）"},
    {"id": "Sulafat", "label": "Sulafat（温暖女声）"},
    {"id": "Puck", "label": "Puck（轻快男声）"},
    {"id": "Charon", "label": "Charon（解说男声）"},
    {"id": "Fenrir", "label": "Fenrir（兴奋男声）"},
    {"id": "Orus", "label": "Orus（坚定男声）"},
    {"id": "Enceladus", "label": "Enceladus（气声男声）"},
    {"id": "Iapetus", "label": "Iapetus（清晰男声）"},
    {"id": "Umbriel", "label": "Umbriel（随和男声）"},
    {"id": "Algieba", "label": "Algieba（顺滑男声）"},
    {"id": "Algenib", "label": "Algenib（沙哑男声）"},
    {"id": "Rasalgethi", "label": "Rasalgethi（解说男声）"},
    {"id": "Alnilam", "label": "Alnilam（坚定男声）"},
    {"id": "Schedar", "label": "Schedar（平稳男声）"},
    {"id": "Achird", "label": "Achird（亲切男声）"},
    {"id": "Zubenelgenubi", "label": "Zubenelgenubi（随意男声）"},
    {"id": "Sadachbia", "label": "Sadachbia（活泼男声）"},
    {"id": "Sadaltager", "label": "Sadaltager（男声）"},
]


def list_voices() -> List[Dict[str, str]]:
    return [{**v, "engine": "gemini"} for v in GEMINI_VOICES]


def voice_ids() -> set:
    return {v["id"] for v in GEMINI_VOICES}


def request_body(text: str, voice: str) -> Dict[str, object]:
    return {
        "contents": [{
            "role": "user",
            "parts": [{"text": text}],
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"voice": voice}},
        },
    }


def pcm_of(payload: Dict[str, object]) -> bytes:
    try:
        parts = payload["candidates"][0]["content"]["parts"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return b""
    out = bytearray()
    for part in parts:
        if not isinstance(part, dict):
            continue
        inline = part.get("inlineData") or part.get("inline_data") or {}
        if not isinstance(inline, dict):
            continue
        data = inline.get("data")
        if not data:
            continue
        raw = base64.b64decode(str(data))
        if raw.startswith(b"RIFF"):
            raw = _wav_pcm(raw)
        out.extend(raw)
    return bytes(out)


def _wav_pcm(raw: bytes) -> bytes:
    if len(raw) < 44 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        return raw
    pos = 12
    while pos + 8 <= len(raw):
        chunk = raw[pos:pos + 4]
        size = int.from_bytes(raw[pos + 4:pos + 8], "little")
        start = pos + 8
        if chunk == b"data":
            return raw[start:start + size]
        pos = start + size + (size & 1)
    return raw


async def synthesize_pcm(text: str, voice: str, api_key: str) -> AsyncIterator[bytes]:
    if not api_key:
        raise RuntimeError(
            "Gemini 合成需要 API Key。在设置 → AI 对话里选 Google Gemini 并填写，或设置环境变量 GEMINI_API_KEY。"
        )
    if voice not in voice_ids():
        raise ValueError(f"音色「{voice}」不在 Gemini 预置列表里")
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=8), trust_env=False) as client:
        async with client.stream(
            "POST",
            GEMINI_TTS_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=request_body(text, voice),
        ) as resp:
            if resp.status_code != 200:
                raw = await resp.aread()
                detail = raw.decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"Gemini 合成失败 HTTP {resp.status_code}：{detail}")
            buf = ""
            async for piece in resp.aiter_text():
                buf += piece
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    pcm = _pcm_from_sse_line(line)
                    if pcm:
                        yield pcm
            pcm = _pcm_from_sse_line(buf)
            if pcm:
                yield pcm


def _pcm_from_sse_line(line: str) -> bytes:
    text = (line or "").strip()
    if not text or text.startswith(":"):
        return b""
    if text.startswith("data:"):
        text = text[5:].strip()
    if not text or text == "[DONE]":
        return b""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return b""
    if isinstance(payload, list):
        out = bytearray()
        for row in payload:
            if isinstance(row, dict):
                out.extend(pcm_of(row))
        return bytes(out)
    if isinstance(payload, dict):
        return pcm_of(payload)
    return b""
