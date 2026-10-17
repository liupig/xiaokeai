"""Gemini 短句识别：把切好的 wav 内嵌进 generateContent。

和对话、朗读、gemini-embedding 共用 AI Studio 的那一把 Key。
"""
from __future__ import annotations

import base64
from typing import Any, Dict

import httpx

GEMINI_ASR_MODEL = "gemini-2.5-flash"
GEMINI_ASR_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_ASR_MODEL}:generateContent"
)


def request_body(wav: bytes) -> Dict[str, Any]:
    return {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": "Transcribe the speech in this audio. Reply with only the transcript, in the original language."},
                {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav).decode("ascii")}},
            ],
        }],
    }


def text_of(payload: Dict[str, Any]) -> str:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    chunks = []
    for part in parts:
        if isinstance(part, dict) and part.get("text"):
            chunks.append(str(part["text"]))
    return "".join(chunks).strip()


async def transcribe(wav: bytes, api_key: str) -> str:
    if not api_key:
        raise RuntimeError(
            "Gemini 识别需要 API Key。在设置 → AI 对话里选 Google Gemini 并填写，或设置环境变量 GEMINI_API_KEY。"
        )
    if len(wav) > 15 * 1024 * 1024:
        raise RuntimeError("这段语音太长，Gemini 单次内嵌音频请保持在短句。")
    async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=8), trust_env=False) as client:
        resp = await client.post(
            GEMINI_ASR_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=request_body(wav),
        )
    if resp.status_code != 200:
        detail = (resp.text or "")[:300]
        raise RuntimeError(f"Gemini 识别失败 HTTP {resp.status_code}：{detail}")
    try:
        return text_of(resp.json())
    except Exception as exc:
        raise RuntimeError(f"Gemini 识别结果无法解析：{exc}") from exc
