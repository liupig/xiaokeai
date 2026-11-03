"""小米 MiMo-V2.5-TTS：预置音色，24kHz PCM16 流式。

目标文本放在 assistant；语气放在 user，也可以在正文开头加 (风格)。
官方预置音色只有这 9 个。音色设计和复刻是另外两个模型，不在这张表里。
"""
from __future__ import annotations

import base64
import json
import re
from typing import AsyncIterator, Dict, List, Tuple

import httpx

MODEL = "mimo-v2.5-tts"
SAMPLE_RATE = 24000
TOKEN_PLAN_BASE = "https://token-plan-cn.xiaomimimo.com/v1"
API_BASE = "https://api.xiaomimimo.com/v1"

# 官方预置音色。中国集群的 mimo_default 实际是冰糖。
MIMO_VOICES: List[Dict[str, str]] = [
    {"id": "冰糖", "label": "冰糖（甜美女声）", "lang": "zh-CN"},
    {"id": "茉莉", "label": "茉莉（清亮女声）", "lang": "zh-CN"},
    {"id": "苏打", "label": "苏打（青年男声）", "lang": "zh-CN"},
    {"id": "白桦", "label": "白桦（沉稳男声）", "lang": "zh-CN"},
    {"id": "mimo_default", "label": "MiMo 默认（中国集群为冰糖）", "lang": "zh-CN"},
    {"id": "Mia", "label": "Mia（英语女声）", "lang": "en"},
    {"id": "Chloe", "label": "Chloe（英语女声）", "lang": "en"},
    {"id": "Milo", "label": "Milo（英语男声）", "lang": "en"},
    {"id": "Dean", "label": "Dean（英语男声）", "lang": "en"},
]

_EMO = {
    "happy": ("开心", "用明亮轻快的语气说，带着压不住的高兴。"),
    "angry": ("愤怒", "语气凌厉，压着火，但把字说清楚。"),
    "sad": ("悲伤", "声音低一点，带着委屈，慢慢说。"),
    "relaxed": ("温柔", "温柔放松，像在身边慢慢说。"),
    "neutral": ("平静", "平静自然地说，不要夸张。"),
}
_CUE = re.compile(r"(?:emo:)?([A-Za-z_]+)(?::([0-9]*\.?[0-9]+))?$")


def list_voices() -> List[Dict[str, str]]:
    return [{**v, "engine": "mimo"} for v in MIMO_VOICES]


def voice_ids() -> set:
    return {v["id"] for v in MIMO_VOICES}


def resolve_base(api_key: str, llm_base: str = "") -> str:
    base = (llm_base or "").strip().rstrip("/")
    if "xiaomimimo.com" in base.lower():
        return base
    if (api_key or "").startswith("tp-"):
        return TOKEN_PLAN_BASE
    return API_BASE


def performance(instruct: str) -> Tuple[str, str]:
    """情绪记号变成 (风格) 和一句指导。自由文本只当指导。"""
    raw = (instruct or "").strip()
    if not raw:
        return "", ""
    matched = _CUE.fullmatch(raw)
    if not matched or matched.group(1).lower() not in _EMO:
        return "", raw
    tag, line = _EMO[matched.group(1).lower()]
    number = matched.group(2)
    if number:
        try:
            strength = float(number)
        except ValueError:
            strength = 0.85
        if strength >= 0.9:
            tag = f"非常{tag}"
            line = "情绪很满。" + line
        elif strength <= 0.45:
            tag = f"淡淡的{tag}"
            line = "情绪很轻。" + line
    return tag, line


def request_body(text: str, voice: str, instruct: str = "", stream: bool = True) -> Dict:
    spoken = (text or "").strip()
    tag, direction = performance(instruct)
    if tag and not spoken.startswith(("(", "（", "[")):
        spoken = f"({tag}){spoken}"
    messages: List[Dict[str, str]] = []
    if direction:
        messages.append({"role": "user", "content": direction})
    messages.append({"role": "assistant", "content": spoken})
    return {
        "model": MODEL,
        "messages": messages,
        "audio": {"format": "pcm16" if stream else "wav", "voice": voice},
        "stream": stream,
    }


def audio_bytes(obj: Dict) -> bytes:
    choices = obj.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return b""
    choice = choices[0]
    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    audio = delta.get("audio") or message.get("audio") or {}
    if not isinstance(audio, dict):
        return b""
    data = audio.get("data") or ""
    if not isinstance(data, str) or not data.strip():
        return b""
    return base64.b64decode(data)


def pcm_from_sse_line(line: str) -> bytes:
    raw = (line or "").strip()
    if not raw or raw.startswith(":"):
        return b""
    if raw.startswith("data:"):
        raw = raw[5:].strip()
    if not raw or raw == "[DONE]":
        return b""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return b""
    if not isinstance(obj, dict):
        return b""
    err = obj.get("error")
    if isinstance(err, dict) and err.get("message"):
        raise RuntimeError(str(err["message"]))
    return audio_bytes(obj)


async def synthesize_pcm(
    text: str, voice: str, api_key: str, instruct: str = "", llm_base: str = "",
) -> AsyncIterator[bytes]:
    if not api_key:
        raise RuntimeError("小米合成需要 API Key。把 XIAOMI_KEY 写进 companion/.env，或在设置里选小米 MiMo 并填写。")
    if voice not in voice_ids():
        raise ValueError(f"音色「{voice}」不在小米预置列表里")
    body = request_body(text, voice, instruct, stream=True)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "api-key": api_key,
        "Content-Type": "application/json",
    }
    url = f"{resolve_base(api_key, llm_base)}/chat/completions"
    timeout = httpx.Timeout(60, connect=10)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code != 200:
                raw = await resp.aread()
                detail = raw.decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"小米合成失败 HTTP {resp.status_code}：{detail}")
            ctype = (resp.headers.get("content-type") or "").lower()
            if "text/event-stream" not in ctype:
                raw = await resp.aread()
                try:
                    obj = json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"小米合成返回的不是音频：{raw[:180]!r}") from exc
                pcm = audio_bytes(obj if isinstance(obj, dict) else {})
                if pcm:
                    yield pcm
                return
            async for line in resp.aiter_lines():
                pcm = pcm_from_sse_line(line)
                if pcm:
                    yield pcm
