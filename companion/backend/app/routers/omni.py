"""MiniCPM-o 4.5 Omni 测试接口。"""
import json
from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..services import omni_minicpm, settings_store

router = APIRouter(prefix="/api/omni", tags=["omni"])


class OmniTestBody(BaseModel):
    text: str = ""
    mode: str = "speech"  # chat = 文字理解；speech = Realtime 语音
    image_b64: str = ""
    chat_url: str = ""
    realtime_host: str = ""
    api_key: str = ""
    model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""


def _merge_conf(body: OmniTestBody, session: Session) -> Dict[str, Any]:
    saved = (settings_store.get_all(session).get("omni") or {})
    llm = settings_store.get_all(session).get("llm") or {}
    key = (body.api_key or saved.get("api_key") or "").strip()
    llm_key = (body.llm_api_key or llm.get("api_key") or "").strip()
    llm_base = (body.llm_base_url or llm.get("base_url") or "").strip()
    if not key and "modelbest.cn" in llm_base.lower():
        key = llm_key
    return {
        "chat_url": (body.chat_url or saved.get("chat_url") or "").strip(),
        "realtime_host": (body.realtime_host or saved.get("realtime_host") or "").strip(),
        "api_key": key,
        "model": (body.model or saved.get("model") or "").strip(),
    }


@router.get("/status")
def omni_status(session: Session = Depends(get_session)) -> Dict[str, Any]:
    saved = settings_store.get_all(session).get("omni") or {}
    cfg = omni_minicpm.conf_from({
        "chat_url": saved.get("chat_url") or "",
        "realtime_host": saved.get("realtime_host") or "",
        "api_key": saved.get("api_key") or "",
        "model": saved.get("model") or "",
    })
    return {
        "ok": True,
        "chat_url": cfg["chat_url"],
        "realtime_host": cfg["realtime_host"],
        "model": cfg["model"],
        "has_key": bool(cfg["api_key"]),
        "sample_rate": omni_minicpm.SAMPLE_RATE,
    }


@router.post("/test")
async def omni_test(body: OmniTestBody, session: Session = Depends(get_session)):
    conf = _merge_conf(body, session)
    session.commit()
    session.close()
    mode = (body.mode or "speech").strip().lower()
    if mode not in ("chat", "speech"):
        mode = "speech"
    agen = (
        omni_minicpm.stream_speech(body.text, image_b64=body.image_b64, conf=conf)
        if mode == "speech"
        else omni_minicpm.stream_chat(body.text, image_b64=body.image_b64, conf=conf)
    )

    async def sse():
        try:
            async for ev in agen:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Audio-Format": "pcm_s16le",
            "X-Audio-Rate": str(omni_minicpm.SAMPLE_RATE),
        },
    )
