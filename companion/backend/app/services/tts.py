"""语音合成：在线 edge-tts 与离线 Qwen3-TTS 分开发动机。"""
from typing import AsyncGenerator, Dict, List

import edge_tts

from . import tts_cosy
from . import tts_eleven
from . import tts_gemini
from . import tts_openai
from . import tts_qwen
from . import tts_volc

EDGE_VOICES = [
    {"id": "zh-CN-XiaoyiNeural", "label": "晓伊（活泼少女）"},
    {"id": "zh-CN-XiaoxiaoNeural", "label": "晓晓（温柔女声）"},
    {"id": "zh-CN-YunxiNeural", "label": "云希（少年）"},
    {"id": "zh-CN-YunjianNeural", "label": "云健（青年男声）"},
    {"id": "zh-CN-YunyangNeural", "label": "云扬（主持）"},
    {"id": "zh-CN-liaoning-XiaobeiNeural", "label": "晓北（东北话）"},
    {"id": "zh-TW-HsiaoChenNeural", "label": "晓臻（台湾腔）", "lang": "zh-CN"},
    {"id": "en-US-AriaNeural", "label": "Aria（英语）", "lang": "en"},
    {"id": "en-US-JennyNeural", "label": "Jenny（英语）", "lang": "en"},
    {"id": "en-US-GuyNeural", "label": "Guy（英语男声）", "lang": "en"},
    {"id": "ja-JP-NanamiNeural", "label": "七海（日语）", "lang": "ja"},
    {"id": "ko-KR-SunHiNeural", "label": "SunHi（韩语）", "lang": "ko"},
]

# 兼容旧 import
VOICES = EDGE_VOICES


def list_voices(engine: str = "") -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for v in EDGE_VOICES:
        items.append({**v, "engine": "edge"})
    for v in tts_qwen.QWEN_VOICES:
        items.append({"id": v["id"], "label": v["label"], "engine": "qwen"})
    for v in tts_cosy.list_voices():
        items.append(v)
    for v in tts_volc.list_voices():
        items.append(v)
    for v in tts_openai.list_voices():
        items.append(v)
    for v in tts_eleven.list_voices():
        items.append(v)
    for v in tts_gemini.list_voices():
        items.append(v)
    if engine:
        items = [x for x in items if x["engine"] == engine]
    return items


def engine_voice_ids(engine: str) -> set:
    return {v["id"] for v in list_voices(engine)}


def resolve_voice(engine: str, voice: str, saved: str = "") -> str:
    """只接受当前引擎支持的音色。空则用已保存的；都不合法则报错，绝不改成别的音色。"""
    allowed = engine_voice_ids(engine)
    chosen = (voice or "").strip()
    if chosen:
        if chosen not in allowed:
            raise ValueError(f"音色「{chosen}」不被 {engine} 支持")
        return chosen
    saved = (saved or "").strip()
    if saved in allowed:
        return saved
    raise ValueError("未选择音色")


def _edge_host() -> None:
    """旧的 Bing 朗读地址从 2026-10 起只收 v2 令牌，当前 edge-tts 仍发 v1，握手会被 403。新主机还收旧令牌。"""
    import edge_tts.communicate as cm
    from edge_tts.constants import TRUSTED_CLIENT_TOKEN
    cm.WSS_URL = (
        "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
        f"?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
    )


async def synthesize_edge(text: str, voice: str = "zh-CN-XiaoyiNeural",
                          rate: str = "+0%") -> AsyncGenerator[bytes, None]:
    _edge_host()
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


# 旧接口：仅 edge-tts
async def synthesize(text: str, voice: str = "zh-CN-XiaoyiNeural",
                     rate: str = "+0%") -> AsyncGenerator[bytes, None]:
    async for chunk in synthesize_edge(text, voice, rate):
        yield chunk
