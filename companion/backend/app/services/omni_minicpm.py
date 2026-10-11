"""MiniCPM-o 4.5 Omni：云端 Chat Completions + Realtime 全双工协议。

本进程不能直接 load PyTorch 权重：官方要求 transformers==4.51.0，
而本地 Qwen3-TTS 钉死 4.57.3。本地自建 Gateway 时把 realtime_host 指过去即可。

  文字 / 图理解   POST {chat_url}/chat/completions   模型 MiniCPM-O-4.5-9B
  Omni 语音        WSS  {realtime_host}/v1/realtime?mode=chat
"""
from __future__ import annotations

import asyncio
import base64
import json
import ssl
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx
import numpy as np

SAMPLE_RATE = 24000
DEFAULT_CHAT_URL = "https://api.modelbest.cn/v1"
DEFAULT_REALTIME_HOST = "https://minicpmo45.modelbest.cn"
DEFAULT_MODEL = "MiniCPM-O-4.5-9B"

ORAL_SYSTEM = (
    "你是虚拟陪伴角色。用口语中文短句回答，像真人聊天。"
    "不要 markdown、列表、括号旁白。"
)


def oral_system() -> str:
    from ..locale_pack import current_reply
    if current_reply() == "zh-CN":
        return ORAL_SYSTEM
    if current_reply() == "ja":
        return "あなたは仮想の相手です。短い話し言葉の日本語で返す。markdown、箇条書き、括弧のト書きは使わない。"
    if current_reply() == "ko":
        return "당신은 가상 상대다. 짧은 한국어 구어로 답한다. markdown, 목록, 괄호 지문은 쓰지 않는다."
    return (
        "You are a virtual companion. Answer in short spoken English, like a person. "
        "No markdown, no lists, no parenthetical stage directions."
    )


def conf_from(raw: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    from . import settings_store

    raw = dict(raw or {})
    env = settings_store.env_omni()
    chat_url = (raw.get("chat_url") or env.get("chat_url") or DEFAULT_CHAT_URL).rstrip("/")
    host = (raw.get("realtime_host") or env.get("realtime_host") or DEFAULT_REALTIME_HOST).rstrip("/")
    model = (raw.get("model") or env.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    key = (raw.get("api_key") or "").strip() or (env.get("api_key") or "")
    return {
        "chat_url": chat_url,
        "realtime_host": host,
        "api_key": key,
        "model": model,
    }


def _auth_headers(api_key: str) -> Dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def _data_url(image_b64: str) -> str:
    blob = (image_b64 or "").strip()
    if not blob:
        return ""
    if blob.startswith("data:"):
        return blob
    return f"data:image/png;base64,{blob}"


def _user_content(text: str, image_b64: str = "") -> Any:
    text = (text or "").strip() or "你好"
    url = _data_url(image_b64)
    if not url:
        return text
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": url}},
    ]


def f32_b64_to_s16le(audio_b64: str) -> bytes:
    raw = base64.b64decode(audio_b64 or "")
    n = len(raw) // 4
    if n <= 0:
        return b""
    f32 = np.frombuffer(raw[: n * 4], dtype="<f4")
    i16 = np.clip(np.rint(f32 * 32767.0), -32768, 32767).astype("<i2")
    return bytes(i16)


def realtime_ws_url(host: str, mode: str = "chat") -> str:
    parsed = urlparse((host or "").strip() or DEFAULT_REALTIME_HOST)
    if parsed.scheme in ("ws", "wss") and "/v1/realtime" in (parsed.path or ""):
        return host
    scheme = parsed.scheme or "https"
    if scheme in ("http", "https"):
        scheme = "wss" if scheme == "https" else "ws"
    elif scheme not in ("ws", "wss"):
        raise ValueError(f"不支持的 Omni 地址：{host}")
    netloc = parsed.netloc or parsed.path.split("/")[0]
    path = "/v1/realtime"
    return urlunparse((scheme, netloc, path, "", f"mode={mode}", ""))


async def stream_chat(
    text: str,
    *,
    image_b64: str = "",
    conf: Optional[Dict[str, Any]] = None,
    system: str = "",
) -> AsyncIterator[Dict[str, Any]]:
    """OpenAI 兼容文字/图片理解（不产语音）。"""
    cfg = conf_from(conf)
    if not cfg["api_key"]:
        yield {"type": "error", "message": "未填写 MiniCPM-o API Key（platform.modelbest.cn）"}
        return
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": (system or oral_system()).strip()},
        {"role": "user", "content": _user_content(text, image_b64)},
    ]
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 512,
    }
    url = f"{cfg['chat_url']}/chat/completions"
    full = ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15),
                                     trust_env=False) as client:
            async with client.stream(
                "POST", url,
                headers={**_auth_headers(cfg["api_key"]), "Content-Type": "application/json"},
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")[:300]
                    yield {"type": "error", "message": f"Chat Completions {resp.status_code}: {body}"}
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if not delta:
                        continue
                    full += delta
                    yield {"type": "text", "delta": delta}
    except httpx.HTTPError as exc:
        yield {"type": "error", "message": f"网络错误：{exc}"}
        return
    yield {"type": "done", "text": full, "audio": False}


def _ws_connect(url: str, headers: Dict[str, str], insecure: bool = False):
    import websockets

    parsed = urlparse(url)
    ssl_ctx = None
    if parsed.scheme == "wss":
        ssl_ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    kwargs: Dict[str, Any] = {
        "ssl": ssl_ctx,
        "open_timeout": 20,
        "max_size": 32 * 1024 * 1024,
    }
    try:
        return websockets.connect(url, additional_headers=headers or None, **kwargs)
    except TypeError:
        return websockets.connect(url, extra_headers=headers or None, **kwargs)


async def stream_speech(
    text: str,
    *,
    image_b64: str = "",
    conf: Optional[Dict[str, Any]] = None,
    system: str = "",
    max_new_tokens: int = 256,
) -> AsyncIterator[Dict[str, Any]]:
    """Realtime mode=chat，打开 TTS，流式返回文字 + 24kHz s16le。"""
    cfg = conf_from(conf)
    url = realtime_ws_url(cfg["realtime_host"], "chat")
    headers = _auth_headers(cfg["api_key"])
    user_content: Any
    img = _data_url(image_b64)
    if img:
        # Realtime 协议用裸 base64；Chat Completions 才用 data URL
        raw = img.split(",", 1)[-1] if img.startswith("data:") else img
        user_content = [
            {"type": "text", "text": (text or "").strip() or "描述这张图"},
            {"type": "image", "data": raw},
        ]
    else:
        from ..locale_pack import prompts
        user_content = (text or "").strip() or str((prompts().get("omni_default") or "用中文介绍你自己，两句话。"))

    full = ""
    audio_bytes = 0
    try:
        async with _ws_connect(url, headers) as ws:
            inited = False
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "replace")
                msg = json.loads(raw)
                kind = msg.get("type") or ""

                if kind in ("session.queued", "session.queue_update"):
                    yield {
                        "type": "queue",
                        "position": msg.get("position"),
                        "estimated_wait_s": msg.get("estimated_wait_s"),
                        "message": f"排队中，前面还有 {msg.get('position') or '?'} 人",
                    }
                    continue
                if kind in ("session.queue_done", "queue_done") and not inited:
                    await ws.send(json.dumps({
                        "type": "session.init",
                        "payload": {"system_prompt": (system or oral_system()).strip()},
                    }))
                    inited = True
                    continue
                if kind == "session.created":
                    await ws.send(json.dumps({
                        "type": "input.append",
                        "input": {
                            "messages": [
                                {"role": "system", "content": (system or oral_system()).strip()},
                                {"role": "user", "content": user_content},
                            ],
                            "streaming": True,
                            "generation": {
                                "max_new_tokens": max_new_tokens,
                                "length_penalty": 1.1,
                            },
                            "omni_mode": bool(img),
                            "tts": {"enabled": True},
                            "use_tts_template": True,
                            "enable_thinking": False,
                        },
                    }))
                    continue
                if kind == "response.output.delta":
                    branch = msg.get("kind") or ""
                    if branch == "text":
                        delta = msg.get("text") or ""
                        if delta:
                            full += delta
                            yield {"type": "text", "delta": delta}
                    elif branch == "audio" and msg.get("audio"):
                        pcm = f32_b64_to_s16le(msg["audio"])
                        if pcm:
                            audio_bytes += len(pcm)
                            yield {
                                "type": "audio",
                                "rate": SAMPLE_RATE,
                                "pcm_b64": base64.b64encode(pcm).decode("ascii"),
                            }
                    elif branch == "listen":
                        yield {"type": "listen"}
                    continue
                if kind == "response.done":
                    done_text = (msg.get("text") or "").strip()
                    if done_text and not full:
                        full = done_text
                        yield {"type": "text", "delta": done_text}
                    try:
                        await ws.send(json.dumps({"type": "session.close", "reason": "turn_done"}))
                    except Exception:
                        pass
                    break
                if kind == "session.closed":
                    break
                if kind == "error":
                    err = msg.get("error") or {}
                    yield {
                        "type": "error",
                        "message": err.get("message") or json.dumps(msg, ensure_ascii=False)[:240],
                    }
                    return
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "Realtime 等待超时（可能在排队或网络不通）"}
        return
    except Exception as exc:
        yield {"type": "error", "message": f"Realtime 失败：{exc}"}
        return
    yield {"type": "done", "text": full, "audio": audio_bytes > 0, "audio_bytes": audio_bytes}
