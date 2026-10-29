"""设置接口。"""
from typing import Any, Dict
import threading

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..paths import content_status
from ..services import content as content_svc
from ..services import settings_store
from ..services.llm import test_connection, test_messages

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ContentBody(BaseModel):
    path: str = ""


@router.post("/test_llm")
async def test_llm(conf: Dict[str, Any]) -> Dict[str, Any]:
    """对话模型和技能目录模型都测。技能目录没另填时只测对话。"""
    from ..modules.harness.service import harness_llm

    chat = await test_connection(conf)
    other = harness_llm(conf)
    skill = await test_messages(other)
    return {
        "ok": bool(chat.get("ok")) and bool(skill.get("ok")),
        "message": f"对话：{chat.get('message')}\n技能目录：{skill.get('message')}",
    }


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
    prev_mods = prev.get("modules") or {}
    now_mods = runtime.get("modules") or {}
    if bool(prev_mods.get("glance", False)) != bool(now_mods.get("glance", False)):
        try:
            from ..modules.harness.service import release as harness_release
            harness_release()
        except Exception:
            pass
        if not bool(now_mods.get("glance", False)):
            try:
                from ..modules.glance.along import stop as along_stop
                along_stop()
            except Exception:
                pass
    if bool(prev_mods.get("live_douyin", False)) and not bool(now_mods.get("live_douyin", False)):
        try:
            from ..modules.live.douyin.listen import stop as live_douyin_stop
            live_douyin_stop()
        except Exception:
            pass
    if not bool(now_mods.get("codewatch", True)):
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
    elif mem_on:
        prev_emb = str(((prev.get("memory") or {}).get("embedder") or "auto"))
        now_emb = str(((runtime.get("memory") or {}).get("embedder") or "auto"))
        prev_llm = prev.get("llm") or {}
        now_llm = runtime.get("llm") or {}
        cred_changed = (
            (prev_llm.get("api_key") or "") != (now_llm.get("api_key") or "")
            or (prev_llm.get("base_url") or "") != (now_llm.get("base_url") or "")
        )
        if prev_emb != now_emb or cred_changed:
            threading.Thread(target=_reload_memory_index, daemon=True).start()
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


def _reload_memory_index() -> None:
    try:
        from ..modules.memory import worker as memory_worker
        memory_worker.reload()
    except Exception as exc:
        print(f"[memory] reload after settings failed: {exc}")
