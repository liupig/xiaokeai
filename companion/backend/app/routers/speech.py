"""语音接口：ASR / TTS 在线与离线分开，可单独设置。"""
import asyncio
import threading
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..services import asr, asr_ali, asr_eleven, asr_gemini, asr_openai, asr_volc, settings_store, tts
from ..services import cloud_key
from ..services import tts_cosy
from ..services import tts_eleven
from ..services import tts_gemini
from ..services import tts_openai
from ..services import tts_qwen
from ..services import tts_volc
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


_EDGE_QWEN = {
    "zh-CN-XiaoyiNeural": "Serena",
    "zh-CN-XiaoxiaoNeural": "Vivian",
    "zh-CN-liaoning-XiaobeiNeural": "Vivian",
    "zh-TW-HsiaoChenNeural": "Serena",
    "zh-CN-YunxiNeural": "Eric",
    "zh-CN-YunjianNeural": "Dylan",
    "zh-CN-YunyangNeural": "Uncle_Fu",
    "en-US-GuyNeural": "Ryan",
    "en-US-DavisNeural": "Aiden",
    "ja-JP-NanamiNeural": "Ono_Anna",
    "ja-JP-AoiNeural": "Ono_Anna",
    "ja-JP-MayuNeural": "Ono_Anna",
    "ko-KR-SunHiNeural": "Sohee",
    "ko-KR-YuJinNeural": "Sohee",
    "ko-KR-SoonBokNeural": "Sohee",
}


def _qwen_stand_in(voice: str) -> str:
    known = {row["id"] for row in tts_qwen.QWEN_VOICES}
    if voice in known:
        return voice
    return _EDGE_QWEN.get(voice, "Serena")


async def _speak_qwen(req: TTSRequest, conf: Dict[str, Any], request: Request, all_conf: Dict[str, Any], voice: str):
    try:
        qwen_size = tts_qwen.normalize_size(req.qwen_size or conf.get("qwen_size") or "0.6b")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    instruct = tts_qwen.resolve_instruct(
        req.qwen_style or conf.get("qwen_style") or "",
        req.instruct or conf.get("qwen_instruct") or "",
    )
    from ..locale_pack import normalize, reply_of
    reply = normalize(reply_of(all_conf))
    if reply != "zh-CN" and any("\u4e00" <= ch <= "\u9fff" for ch in instruct):
        instruct = ""
    cancel = threading.Event()
    agen = tts_qwen.synthesize_pcm(
        req.text, voice, qwen_size, instruct, cancel, tts_qwen.qwen_language(reply),
    )
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
        talk_log.write("tts", f"本地失败 {exc}")
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
                if chunk:
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
        from ..locale_pack import align_voice, reply_of
        all_conf = settings_store.get_all(session)
        voice = align_voice(engine, voice, reply_of(all_conf))
        voice = tts.resolve_voice(engine, voice, voice)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    llm = settings_store.apply_llm_overlay(dict(all_conf.get("llm") or {}))
    session.commit()
    session.close()
    rate = req.rate or conf.get("rate") or "+0%"
    if engine == "cosy":
        api_key = cloud_key.ali_key(llm)
        if not api_key.startswith("sk-"):
            raise HTTPException(
                400,
                "阿里合成需要百炼 API Key（sk-）。填在设置 → AI 对话，和识别、向量共用这一把。",
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
    if engine == "volc":
        agen = tts_volc.synthesize_mp3(req.text, voice, cloud_key.volc_speech_key(llm))
        try:
            first = await anext(agen)
        except StopAsyncIteration:
            raise HTTPException(503, "火山合成未返回音频") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, str(exc)) from exc

        async def volc_gen():
            yield first
            async for chunk in agen:
                yield chunk

        return StreamingResponse(
            volc_gen(),
            media_type="audio/mpeg",
            headers={
                "X-Audio-Format": "mp3",
                "X-Audio-Rate": str(tts_volc.SAMPLE_RATE),
                "Cache-Control": "no-store",
                "Access-Control-Expose-Headers": "X-Audio-Format, X-Audio-Rate",
            },
        )
    if engine in ("openai", "eleven"):
        if engine == "openai":
            agen = tts_openai.synthesize_mp3(req.text, voice, cloud_key.openai_key(llm))
            rate = tts_openai.SAMPLE_RATE
            label = "OpenAI"
        else:
            agen = tts_eleven.synthesize_mp3(req.text, voice, cloud_key.eleven_key(llm))
            rate = tts_eleven.SAMPLE_RATE
            label = "ElevenLabs"
        try:
            first = await anext(agen)
        except StopAsyncIteration:
            raise HTTPException(503, f"{label}合成未返回音频") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, str(exc)) from exc

        async def mp3_gen():
            yield first
            async for chunk in agen:
                yield chunk

        return StreamingResponse(
            mp3_gen(),
            media_type="audio/mpeg",
            headers={
                "X-Audio-Format": "mp3",
                "X-Audio-Rate": str(rate),
                "Cache-Control": "no-store",
                "Access-Control-Expose-Headers": "X-Audio-Format, X-Audio-Rate",
            },
        )
    if engine == "gemini":
        agen = tts_gemini.synthesize_pcm(req.text, voice, cloud_key.gemini_key(llm))
        try:
            first = await anext(agen)
        except StopAsyncIteration:
            raise HTTPException(503, "Gemini 合成未返回音频") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, str(exc)) from exc

        async def gemini_gen():
            yield first
            async for chunk in agen:
                yield chunk

        return StreamingResponse(
            gemini_gen(),
            media_type="application/octet-stream",
            headers={
                "X-Audio-Format": "pcm_s16le",
                "X-Audio-Rate": str(tts_gemini.SAMPLE_RATE),
                "Cache-Control": "no-store",
                "Access-Control-Expose-Headers": "X-Audio-Format, X-Audio-Rate",
            },
        )
    if engine == "qwen":
        return await _speak_qwen(req, conf, request, all_conf, voice)
    agen = tts.synthesize_edge(req.text, voice, rate).__aiter__()
    try:
        first = await agen.__anext__()
    except StopAsyncIteration:
        raise HTTPException(503, "edge TTS 没有声音") from None
    except Exception as exc:
        talk_log.write("tts", f"edge失败 {exc}")
        limited = any(code in str(exc) for code in ("429", "403"))
        if not limited:
            raise HTTPException(503, "edge TTS 失败") from exc
        local = _qwen_stand_in(voice)
        talk_log.write("tts", f"edge被限流，改走本地 {local}")
        req.engine = "qwen"
        req.voice = local
        req.qwen_style = ""
        return await _speak_qwen(req, conf, request, all_conf, local)

    async def edge_gen():
        try:
            yield first
            async for chunk in agen:
                yield chunk
        finally:
            closer = getattr(agen, "aclose", None)
            if closer:
                try:
                    await closer()
                except Exception:
                    pass

    return StreamingResponse(
        edge_gen(),
        media_type="audio/mpeg",
        headers={
            "X-Audio-Format": "mp3",
            "Cache-Control": "no-store",
            "Access-Control-Expose-Headers": "X-Audio-Format, X-Audio-Rate",
        },
    )


@router.post("/stt")
async def stt_endpoint(file: UploadFile = File(...), session: Session = Depends(get_session)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "音频为空")
    all_conf = settings_store.get_all(session)
    engine = ((all_conf.get("stt") or {}).get("engine") or "").strip().lower()
    llm = settings_store.apply_llm_overlay(dict(all_conf.get("llm") or {}))
    session.commit()
    session.close()
    try:
        if engine == "ali":
            text = await asr_ali.transcribe(data, cloud_key.ali_key(llm))
        elif engine == "volc":
            text = await asr_volc.transcribe(data, cloud_key.volc_speech_key(llm))
        elif engine == "openai":
            text = await asr_openai.transcribe(data, cloud_key.openai_key(llm))
        elif engine == "eleven":
            text = await asr_eleven.transcribe(data, cloud_key.eleven_key(llm))
        elif engine == "gemini":
            text = await asr_gemini.transcribe(data, cloud_key.gemini_key(llm))
        else:
            text = await asyncio.to_thread(asr.transcribe, data)
    except Exception as exc:
        talk_log.write("asr", f"失败 {exc}")
        label = {
            "ali": "阿里", "volc": "火山", "openai": "OpenAI",
            "eleven": "ElevenLabs", "gemini": "Gemini",
        }.get(engine, "本地")
        raise HTTPException(503, f"{label} ASR 失败：{exc}") from exc
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
