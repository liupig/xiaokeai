"""ElevenLabs 短句识别：Scribe v2，上传切好的 wav。

Key 用环境变量 ELEVENLABS_API_KEY。这家没有对话和向量。
"""
from __future__ import annotations

from typing import Any, Dict

import httpx

ELEVEN_ASR_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVEN_ASR_MODEL = "scribe_v2"


def text_of(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    rows = payload.get("transcripts")
    if isinstance(rows, list):
        parts = []
        for row in rows:
            if isinstance(row, dict):
                parts.append(str(row.get("text") or ""))
            elif isinstance(row, str):
                parts.append(row)
        return "".join(parts).strip()
    return ""


async def transcribe(wav: bytes, api_key: str) -> str:
    if not api_key:
        raise RuntimeError("ElevenLabs 识别需要 API Key。请设置环境变量 ELEVENLABS_API_KEY。")
    if len(wav) > 24 * 1024 * 1024:
        raise RuntimeError("这段语音太长。")
    async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=8), trust_env=False) as client:
        resp = await client.post(
            ELEVEN_ASR_URL,
            headers={"xi-api-key": api_key},
            files={"file": ("clip.wav", wav, "audio/wav")},
            data={"model_id": ELEVEN_ASR_MODEL},
        )
    if resp.status_code != 200:
        detail = (resp.text or "")[:300]
        raise RuntimeError(f"ElevenLabs 识别失败 HTTP {resp.status_code}：{detail}")
    try:
        return text_of(resp.json())
    except Exception as exc:
        raise RuntimeError(f"ElevenLabs 识别结果无法解析：{exc}") from exc
