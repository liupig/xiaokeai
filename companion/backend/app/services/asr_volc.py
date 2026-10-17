"""火山豆包流式语音识别 2.0。

整段 wav 走流式输入（nostream）：发完最后一包再拿整句，和现在「切一段再识别」一致。
鉴权是新版控制台的 X-Api-Key，资源 volc.seedasr.sauc.duration。
"""
from __future__ import annotations

import asyncio
import gzip
import inspect
import json
import struct
import uuid
from typing import Any, Dict, Optional

import numpy as np

VOLC_ASR_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
VOLC_ASR_RESOURCE = "volc.seedasr.sauc.duration"

_FULL = 0x1
_AUDIO = 0x2
_ERROR = 0xF
_JSON = 0x1
_GZIP = 0x1


def pack_frame(msg_type: int, flags: int, serial: int, compress: int,
               seq: Optional[int], payload: bytes) -> bytes:
    frame = bytes((
        0x11,
        ((msg_type & 0xF) << 4) | (flags & 0xF),
        ((serial & 0xF) << 4) | (compress & 0xF),
        0x00,
    ))
    if flags & 0x01:
        if seq is None:
            raise ValueError("带序号的帧缺少 seq")
        frame += struct.pack(">i", seq)
    frame += struct.pack(">I", len(payload))
    frame += payload
    return frame


def parse_frame(data: bytes) -> Dict[str, Any]:
    if len(data) < 8:
        raise RuntimeError("火山识别回了不完整的帧")
    msg_type = data[1] >> 4
    flags = data[1] & 0x0F
    serial = data[2] >> 4
    compress = data[2] & 0x0F
    off = 4
    seq = None
    if flags & 0x01:
        seq = int.from_bytes(data[off:off + 4], "big", signed=True)
        off += 4
    if msg_type == _ERROR:
        if len(data) < off + 8:
            raise RuntimeError("火山识别错误帧不完整")
        code = int.from_bytes(data[off:off + 4], "big")
        size = int.from_bytes(data[off + 4:off + 8], "big")
        msg = data[off + 8:off + 8 + size].decode("utf-8", "replace")
        raise RuntimeError(f"火山识别失败 {code}：{msg}")
    if len(data) < off + 4:
        raise RuntimeError("火山识别回了不完整的帧")
    size = int.from_bytes(data[off:off + 4], "big")
    payload = data[off + 4:off + 4 + size]
    if compress == _GZIP and payload:
        payload = gzip.decompress(payload)
    obj = None
    if serial == _JSON and payload:
        obj = json.loads(payload.decode("utf-8"))
    return {"seq": seq, "last": bool(flags & 0x02), "json": obj}


def text_of(obj: Any) -> str:
    if not isinstance(obj, dict):
        return ""
    result = obj.get("result")
    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    if isinstance(result, list):
        parts = []
        for row in result:
            if isinstance(row, dict) and row.get("text"):
                parts.append(str(row["text"]))
        return "".join(parts).strip()
    return str(obj.get("text") or "").strip()


def wav_to_pcm16_16k(wav: bytes) -> bytes:
    """浏览器送来的 wav 转成 16kHz / 16bit / 单声道 PCM。豆包识别只收这个采样率。"""
    if len(wav) < 44 or wav[:4] != b"RIFF":
        raise RuntimeError("识别需要 wav")
    rate = channels = bits = None
    pcm = b""
    off = 12
    while off + 8 <= len(wav):
        chunk = wav[off:off + 4]
        size = int.from_bytes(wav[off + 4:off + 8], "little")
        body = wav[off + 8:off + 8 + size]
        if chunk == b"fmt " and len(body) >= 16:
            channels = int.from_bytes(body[2:4], "little")
            rate = int.from_bytes(body[4:8], "little")
            bits = int.from_bytes(body[14:16], "little")
        elif chunk == b"data":
            pcm = body
            break
        off += 8 + size + (size & 1)
    if not pcm or not rate or not channels or bits != 16:
        raise RuntimeError("这段 wav 不是 16bit PCM")
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    if channels > 1:
        usable = (len(samples) // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    if rate != 16000 and len(samples) > 1:
        out_n = max(1, int(round(len(samples) * 16000 / rate)))
        src_x = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
        dst_x = np.linspace(0.0, 1.0, num=out_n, endpoint=False)
        samples = np.interp(dst_x, src_x, samples)
    return np.clip(np.rint(samples), -32768, 32767).astype("<i2").tobytes()


def _full_request(seq: int) -> bytes:
    payload = gzip.compress(json.dumps({
        "user": {"uid": "xiaoke"},
        "audio": {"format": "pcm", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": False,
            "result_type": "full",
        },
    }, ensure_ascii=False).encode("utf-8"))
    return pack_frame(_FULL, 0x01, _JSON, _GZIP, seq, payload)


def _audio_request(seq: int, pcm: bytes, last: bool) -> bytes:
    payload = gzip.compress(pcm)
    if last:
        return pack_frame(_AUDIO, 0x03, 0, _GZIP, -abs(seq), payload)
    return pack_frame(_AUDIO, 0x01, 0, _GZIP, seq, payload)


async def transcribe(wav: bytes, api_key: str) -> str:
    if not api_key:
        raise RuntimeError(
            "火山识别需要 API Key。默认用设置 → AI 对话里的那把；"
            "若豆包语音控制台的 Key 和方舟不是同一把，设置环境变量 VOLC_SPEECH_API_KEY。"
        )
    pcm = wav_to_pcm16_16k(wav)
    if len(pcm) < 1600:
        return ""
    import websockets

    req_id = str(uuid.uuid4())
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": VOLC_ASR_RESOURCE,
        "X-Api-Request-Id": req_id,
        "X-Api-Connect-Id": req_id,
        "X-Api-Sequence": "-1",
    }
    connect_kw: Dict[str, Any] = {
        "max_size": 8 * 1024 * 1024,
        "open_timeout": 8,
        "close_timeout": 2,
    }
    names = inspect.signature(websockets.connect).parameters
    if "additional_headers" in names:
        connect_kw["additional_headers"] = headers
    else:
        connect_kw["extra_headers"] = headers
    text = ""
    try:
        async with websockets.connect(VOLC_ASR_URL, **connect_kw) as ws:
            await ws.send(_full_request(1))
            step = 6400
            seq = 2
            for i in range(0, len(pcm), step):
                piece = pcm[i:i + step]
                last = i + step >= len(pcm)
                await ws.send(_audio_request(seq, piece, last))
                seq += 1
            while True:
                raw = await asyncio.wait_for(ws.recv(), 25)
                if isinstance(raw, str):
                    continue
                frame = parse_frame(raw)
                got = text_of(frame.get("json"))
                if got:
                    text = got
                if frame.get("last"):
                    break
    except RuntimeError:
        raise
    except asyncio.TimeoutError as exc:
        if text:
            return text
        raise RuntimeError("火山识别超时") from exc
    except Exception as exc:
        if text:
            return text
        message = str(exc)
        if "401" in message or "403" in message:
            raise RuntimeError(
                "火山识别鉴权失败。方舟对话 Key 和豆包语音 Key 有时不是同一把，"
                "把豆包语音控制台的 API Key 设到 VOLC_SPEECH_API_KEY。"
            ) from exc
        raise RuntimeError(f"火山识别失败：{message}") from exc
    return text
