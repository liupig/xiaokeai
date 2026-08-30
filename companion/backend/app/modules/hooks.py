"""对话管线钩子：chat 路由只调这里，不碰各模块内部。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlmodel import Session

from .flags import enabled


def before_messages(
    session: Session,
    character_id: int,
    mode: str,
    messages: List[Dict[str, str]],
    extra: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    extra = extra or {}
    out = list(messages)
    if enabled(session, "memory"):
        from .memory.worker import inject_memory
        try:
            out = inject_memory(character_id, out)
        except Exception as exc:
            print(f"[memory] inject failed: {exc}")
    if enabled(session, "rewrite") and extra.get("variation"):
        from .rewrite.service import inject_variation
        out = inject_variation(out, str(extra.get("variation") or ""))
    return out


def after_messages(
    session: Session,
    character_id: int,
    mode: str,
    messages: List[Dict[str, str]],
    extra: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """双工提示之后再压一场戏，避免被『半身闲聊』盖掉。"""
    extra = extra or {}
    if not enabled(session, "scenes"):
        return messages
    from .scenes.service import inject_scene
    return inject_scene(session, character_id, messages, extra, mode=mode)


def scene_playing(
    session: Session,
    character_id: int,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    if not enabled(session, "scenes"):
        return False
    from .scenes.service import scene_playing as _playing
    return _playing(session, character_id, extra or {})


def schedule_after_reply(
    character_id: int,
    mode: str,
    user_text: str,
    assistant_text: str,
) -> None:
    if (mode or "user").lower() not in ("user", "qa", ""):
        return
    if not (user_text or "").strip() or not (assistant_text or "").strip():
        return
    from .memory.worker import tick
    try:
        tick(character_id)
    except Exception as exc:
        print(f"[memory] extract tick failed: {exc}")
