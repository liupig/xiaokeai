"""设置接口。"""
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..paths import content_status
from ..services import content as content_svc
from ..services import settings_store
from ..services.llm import test_connection

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ContentBody(BaseModel):
    path: str = ""


@router.post("/test_llm")
async def test_llm(conf: Dict[str, Any]) -> Dict[str, Any]:
    """用面板里正在编辑（未必已保存）的 LLM 配置做连通性测试。"""
    return await test_connection(conf)


@router.get("/content")
def get_content() -> Dict[str, Any]:
    return content_status()


@router.put("/content")
def update_content(body: ContentBody) -> Dict[str, Any]:
    return content_svc.save(body.path)


@router.get("")
def get_settings(session: Session = Depends(get_session)) -> Dict[str, Any]:
    out = settings_store.public_all(session)
    out["content"] = content_status()
    return out


@router.put("")
def update_settings(patch: Dict[str, Any],
                    session: Session = Depends(get_session)) -> Dict[str, Any]:
    from ..modules.memory import worker as memory_worker
    from ..services import autotune

    prev = settings_store.get_all(session)
    patch = autotune.lock_user_override(session, patch)
    patch.pop("content", None)
    settings_store.update(session, patch)
    out = settings_store.public_all(session)
    out["content"] = content_status()
    runtime = settings_store.get_all(session)
    _sync_speech_workers(runtime)
    if not bool((runtime.get("modules") or {}).get("codewatch", True)):
        try:
            from ..modules.codewatch.router import release as codewatch_release
            codewatch_release()
        except Exception:
            pass
    mem_on = bool((runtime.get("modules") or {}).get("memory", True))
    if not mem_on:
        try:
            memory_worker.release()
        except Exception:
            pass
    elif mem_on and not bool((prev.get("modules") or {}).get("memory", True)):
        try:
            memory_worker.clear_boot_failed()
        except Exception:
            pass
    return out


def _sync_speech_workers(conf: Dict[str, Any]) -> None:
    """设置里没选本地引擎就把对应 worker 卸掉，避免空占 CPU/GPU。"""
    from ..services import asr as asr_svc
    from ..services import tts_qwen

    tts_eng = ((conf.get("tts") or {}).get("engine") or "").strip().lower()
    stt_eng = ((conf.get("stt") or {}).get("engine") or "").strip().lower()
    if tts_eng != "qwen":
        tts_qwen.release()
    if stt_eng != "sensevoice":
        asr_svc.release()
