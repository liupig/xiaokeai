"""阿里百炼短句识别：qwen3-asr-flash，OpenAI 兼容 HTTP。

和对话、CosyVoice、text-embedding 共用一把 sk-。
现有域名 dashscope.aliyuncs.com 仍可用，不必填业务空间 ID。
"""
from __future__ import annotations

import base64
from typing import Any, Dict

import httpx

ALI_ASR_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
ALI_ASR_MODEL = "qwen3-asr-flash"


def request_body(wav: bytes) -> Dict[str, Any]:
    data_uri = "data:audio/wav;base64," + base64.b64encode(wav).decode("ascii")
    return {
        "model": ALI_ASR_MODEL,
        "messages": [{
            "role": "user",
            "content": [{
                "type": "input_audio",
                "input_audio": {"data": data_uri},
            }],
        }],
        "stream": False,
        "asr_options": {"enable_itn": True},
    }


def text_of(payload: Dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for row in content:
            if isinstance(row, str):
                parts.append(row)
            elif isinstance(row, dict):
                parts.append(str(row.get("text") or ""))
        return "".join(parts).strip()
    return ""


async def transcribe(wav: bytes, api_key: str) -> str:
    if not api_key:
        raise RuntimeError("阿里识别需要百炼 API Key（sk-）。填在设置 → AI 对话，和合成、向量共用这一把。")
    if len(wav) > 7 * 1024 * 1024:
        raise RuntimeError("这段语音太长，阿里识别单次不超过约 5 分钟。")
    async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=8), trust_env=False) as client:
        resp = await client.post(
            ALI_ASR_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=request_body(wav),
        )
    if resp.status_code != 200:
        detail = ""
        try:
            body = resp.json()
            detail = str(body.get("message") or body.get("error") or body)[:300]
        except Exception:
            detail = (resp.text or "")[:300]
        raise RuntimeError(f"阿里识别失败 HTTP {resp.status_code}：{detail}")
    try:
        return text_of(resp.json())
    except Exception as exc:
        raise RuntimeError(f"阿里识别结果无法解析：{exc}") from exc
