"""OpenAI 短句识别：把切好的 wav 交给 /v1/audio/transcriptions。

官方现在推荐 gpt-transcribe。和朗读、text-embedding 共用一把 Key。
"""
from __future__ import annotations

from typing import Any, Dict

import httpx

OPENAI_ASR_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_ASR_MODEL = "gpt-transcribe"


def text_of(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("text") or "").strip()


async def transcribe(wav: bytes, api_key: str) -> str:
    if not api_key:
        raise RuntimeError(
            "OpenAI 识别需要 API Key。在设置 → AI 对话里选 OpenAI 并填写，或设置环境变量 OPENAI_API_KEY。"
        )
    if len(wav) > 24 * 1024 * 1024:
        raise RuntimeError("这段语音太长，OpenAI 识别单次不超过 25MB。")
    async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=8), trust_env=False) as client:
        resp = await client.post(
            OPENAI_ASR_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("clip.wav", wav, "audio/wav")},
            data={"model": OPENAI_ASR_MODEL},
        )
    if resp.status_code != 200:
        detail = _detail(resp)
        raise RuntimeError(f"OpenAI 识别失败 HTTP {resp.status_code}：{detail}")
    try:
        return text_of(resp.json())
    except Exception as exc:
        raise RuntimeError(f"OpenAI 识别结果无法解析：{exc}") from exc


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        return str(body.get("message") or body)[:300]
    except Exception:
        return (resp.text or "")[:300]
