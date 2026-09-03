"""语音接口：ASR / TTS 在线与离线分开，可单独设置。"""
import asyncio
import threading
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..services import asr, settings_store, tts
from ..services import tts_cosy
from ..services import tts_qwen
from .. import talk_log

router = APIRouter(prefix="/api/speech", tags=["speech"])


class TTSRequest(BaseModel):
    text: str
    voice: str = ""
    rate: str = ""
    engine: str = ""
    qwen_size: str = ""
    qwen_style: str = ""
    instruct: str = ""


class WarmupRequest(BaseModel):
    target: str = "all"  # asr | tts | all
    qwen_size: str = ""


def _tts_conf(session: Session) -> Dict[str, Any]:
    return settings_store.get_all(session).get("tts") or {}


@router.post("/tts")
async def tts_endpoint(req: TTSRequest, request: Request, session: Session = Depends(get_session)):
    if not req.text.strip():
        raise HTTPException(400, "文本为空")
    conf = _tts_conf(session)
    engine = (req.engine or conf.get("engine") or "qwen").strip().lower()
    if engine in ("browser", "off"):
        raise HTTPException(400, "当前引擎不走后端合成")
    try:
        voice = tts.resolve_voice(engine, req.voice, conf.get("voice") or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    rate = req.rate or conf.get("rate") or "+0%"
    if engine == "cosy":
        llm = settings_store.get_all(session).get("llm") or {}
        api_key = (llm.get("api_key") or "").strip()
        if not api_key.startswith("sk-"):
            raise HTTPException(
                400,
                "CosyVoice 需要阿里云百炼 API Key（sk- 开头）。"
                "当前对话 Key 不能共用，请改用「edge-tts 流式」，或在 AI 对话里换成百炼 Key。",
            )
        agen = tts_cosy.synthesize_pcm(req.text, voice, api_key)
        try:
            first = await anext(agen)
        except StopAsyncIteration:
            raise HTTPException(503, "CosyVoice 未返回音频") from None
        except Exception as exc:
            raise HTTPException(503, f"CosyVoice 失败：{exc}") from exc

        async def pcm_gen():
            yield first
            async for chunk in agen:
                yield chunk

        return StreamingResponse(
            pcm_gen(),
            media_type="application/octet-stream",
            headers={
                "X-Audio-Format": "pcm_s16le",
                "X-Audio-Rate": str(tts_cosy.SAMPLE_RATE),
                "Cache-Control": "no-store",
                "Access-Control-Expose-Headers": "X-Audio-Format, X-Audio-Rate",
            },
        )
    if engine == "qwen":
        try:
            qwen_size = tts_qwen.normalize_size(req.qwen_size or conf.get("qwen_size") or "0.6b")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        instruct = tts_qwen.resolve_instruct(
            req.qwen_style or conf.get("qwen_style") or "",
            req.instruct or conf.get("qwen_instruct") or "",
        )
        cancel = threading.Event()
        agen = tts_qwen.synthesize_pcm(req.text, voice, qwen_size, instruct, cancel)
        try:
            first = await anext(agen)
        except StopAsyncIteration:
            cancel.set()
            raise HTTPException(503, "本地 TTS 未返回音频") from None
        except ValueError as exc:
            cancel.set()
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            cancel.set()
            raise HTTPException(503, f"本地 TTS 失败：{exc}") from exc
        except BaseException:
            cancel.set()
            raise

        async def pcm_gen():
            try:
                yield first
                async for chunk in agen:
                    if await request.is_disconnected():
                        break
                    yield chunk
            finally:
                cancel.set()
                try:
                    await agen.aclose()
                except Exception:
                    pass

        return StreamingResponse(
            pcm_gen(),
            media_type="application/octet-stream",
            headers={
                "X-Audio-Format": "pcm_s16le",
                "X-Audio-Rate": str(tts_qwen.SAMPLE_RATE),
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
                "Access-Control-Expose-Headers": "X-Audio-Format, X-Audio-Rate",
            },
        )
    return StreamingResponse(
        tts.synthesize_edge(req.text, voice, rate),
        media_type="audio/mpeg",
        headers={
            "X-Audio-Format": "mp3",
            "Cache-Control": "no-store",
            "Access-Control-Expose-Headers": "X-Audio-Format, X-Audio-Rate",
        },
    )


@router.post("/stt")
async def stt_endpoint(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "音频为空")
    try:
        text = await asyncio.to_thread(asr.transcribe, data)
    except Exception as exc:
        talk_log.write("asr", f"失败 {exc}")
        raise HTTPException(503, f"本地 ASR 失败：{exc}") from exc
    shown = (text or "").strip()
    talk_log.write("asr", shown)
    return {"text": text}


@router.get("/voices")
def voices(engine: str = ""):
    return tts.list_voices(engine)


@router.get("/status")
def speech_status():
    asr_st = asr.status()
    try:
        tts_st = tts_qwen.status()
    except Exception as exc:
        tts_st = {
            "engine": "qwen", "available": False, "ready": False,
            "loading": False, "downloading": False, "message": str(exc),
        }
    return {"asr": asr_st, "tts": tts_st}


def _run_warmup(target: str, qwen_size: str) -> None:
    try:
        if target in ("asr", "all"):
            asr.warmup(download=True)
        if target in ("tts", "all"):
            tts_qwen.warmup(qwen_size, download=True)
    except Exception as exc:
        if target in ("tts", "all"):
            tts_qwen._state["message"] = str(exc)
        if target in ("asr", "all"):
            asr._state["message"] = str(exc)
    finally:
        if target in ("asr", "all"):
            asr._state["downloading"] = False
        if target in ("tts", "all"):
            tts_qwen._state["loading"] = False
            tts_qwen._state["downloading"] = False


@router.post("/warmup")
def warmup(req: WarmupRequest, session: Session = Depends(get_session)):
    target = (req.target or "all").lower()
    if target not in ("asr", "tts", "all"):
        raise HTTPException(400, "target 必须是 asr / tts / all")
    conf = _tts_conf(session)
    stt_eng = ((settings_store.get_all(session).get("stt") or {}).get("engine") or "").strip().lower()
    tts_eng = (conf.get("engine") or "").strip().lower()
    # 显式 asr/tts 仍照做（设置页「准备模型」）；all 只加载当前选中的本地引擎
    want_asr = target == "asr" or (target == "all" and stt_eng == "sensevoice")
    want_tts = target == "tts" or (target == "all" and tts_eng == "qwen")
    if not want_asr and not want_tts:
        return {"ok": True, "message": "当前未使用本地 ASR/TTS，跳过加载", **speech_status()}
    try:
        qwen_size = tts_qwen.normalize_size(req.qwen_size or conf.get("qwen_size") or "0.6b")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    asr_ready = bool(asr.status().get("ready"))
    tts_st = tts_qwen.status()
    tts_busy = bool(tts_st.get("loading") or tts_st.get("downloading"))
    tts_ready = bool(tts_st.get("ready")) and (tts_st.get("size") or "") == qwen_size
    if want_asr and asr.status().get("downloading"):
        return {"ok": True, "message": "ASR 已在准备中", **speech_status()}
    if want_tts and tts_busy and not tts_ready:
        return {"ok": True, "message": "TTS 已在加载中", **speech_status()}
    asr_need = want_asr and not asr_ready
    tts_need = want_tts and not tts_ready
    if not asr_need and not tts_need:
        return {"ok": True, "message": "离线模型已在内存中，可直接用", **speech_status()}
    run_target = "all" if asr_need and tts_need else ("asr" if asr_need else "tts")
    if asr_need:
        asr._state["downloading"] = True
        asr._state["message"] = "正在准备 SenseVoice…"
    if tts_need:
        label = tts_qwen.VARIANTS[qwen_size]["label"]
        tts_qwen._state["loading"] = True
        tts_qwen._state["message"] = f"正在加载 Qwen3-TTS {label}…"
    threading.Thread(target=_run_warmup, args=(run_target, qwen_size), daemon=True).start()
    return {"ok": True, "message": "已开始准备模型", **speech_status()}
