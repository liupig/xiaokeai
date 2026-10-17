"""识别、合成、向量共用对话设置里的那一把 Key。

阿里百炼：一把 sk- 覆盖 qwen3-asr-flash、CosyVoice、text-embedding。
火山：对话和向量走方舟；识别和合成走豆包语音，默认也用这把 Key。
豆包语音控制台若另发了 Key，可用环境变量 VOLC_SPEECH_API_KEY 覆盖语音这两项。
OpenAI：对话地址是 api.openai.com 时，同一把 Key 覆盖识别、朗读和向量。
Gemini：对话地址是 generativelanguage.googleapis.com 时同样共用。
ElevenLabs 没有对话模型，Key 放环境变量 ELEVENLABS_API_KEY。
"""
from __future__ import annotations

import os
from typing import Any, Dict


def _chat_key(llm: Dict[str, Any]) -> str:
    return (llm.get("api_key") or "").strip()


def _base(llm: Dict[str, Any]) -> str:
    return (llm.get("base_url") or "").strip().lower()


def ali_key(llm: Dict[str, Any]) -> str:
    key = _chat_key(llm)
    base = _base(llm)
    if key and "dashscope" in base:
        return key
    # OpenAI 的 Key 也是 sk-，不能拿去当百炼。
    if key.startswith("sk-") and "openai.com" not in base:
        return key
    return (os.environ.get("DASHSCOPE_API_KEY") or "").strip()


def volc_speech_key(llm: Dict[str, Any]) -> str:
    override = (os.environ.get("VOLC_SPEECH_API_KEY") or "").strip()
    if override:
        return override
    key = _chat_key(llm)
    base = _base(llm)
    if key and ("volces.com" in base or "volcengine" in base):
        return key
    env = (os.environ.get("ARK_API_KEY") or os.environ.get("VOLC_ARK_API_KEY") or "").strip()
    if env:
        return env
    if key and not key.startswith("sk-") and "googleapis.com" not in base and "openai.com" not in base:
        return key
    return ""


def openai_key(llm: Dict[str, Any]) -> str:
    key = _chat_key(llm)
    if key and "api.openai.com" in _base(llm):
        return key
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def gemini_key(llm: Dict[str, Any]) -> str:
    key = _chat_key(llm)
    if key and "generativelanguage.googleapis.com" in _base(llm):
        return key
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def eleven_key(llm: Dict[str, Any]) -> str:
    override = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if override:
        return override
    key = _chat_key(llm)
    if key and "elevenlabs.io" in _base(llm):
        return key
    return ""
