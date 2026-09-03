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
    tarot_isolate = False
    if enabled(session, "tarot"):
        from .tarot.service import isolate_prompt
        tarot_isolate = isolate_prompt(
            character_id, mode, str(extra.get("user_text") or ""),
        )
    if enabled(session, "memory") and not tarot_isolate:
        from .memory.worker import inject_memory
        try:
            out = inject_memory(character_id, out)
        except Exception as exc:
            print(f"[memory] inject failed: {exc}")
    if enabled(session, "rewrite") and extra.get("variation"):
        from .rewrite.service import inject_variation
        hint = str(extra.get("variation") or "")
        if enabled(session, "tarot"):
            from .tarot.service import active as tarot_active
            if tarot_active(character_id):
                hint = (
                    "同一张牌换个说法再讲一遍。牌名和正逆位不能改。"
                    "不要问要不要再抽，不要说再来一次。"
                )
        out = inject_variation(out, hint)
    if enabled(session, "tarot") and not extra.get("variation"):
        from .tarot.service import apply_user_text
        try:
            apply_user_text(character_id, mode, str(extra.get("user_text") or ""))
        except Exception as exc:
            print(f"[tarot] apply failed: {exc}")
    return out


def after_messages(
    session: Session,
    character_id: int,
    mode: str,
    messages: List[Dict[str, str]],
    extra: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """双工提示之后再压一场戏，避免被『半身闲聊』盖掉。看牌 overlay 放最后，盖过闲聊长短。"""
    extra = extra or {}
    out = list(messages)
    tarot_isolate = False
    if enabled(session, "tarot"):
        from .tarot.service import isolate_prompt
        tarot_isolate = isolate_prompt(
            character_id, mode, str(extra.get("user_text") or ""),
        )
    if enabled(session, "scenes") and not tarot_isolate:
        from .scenes.service import inject_scene
        out = inject_scene(session, character_id, out, extra, mode=mode)
    if enabled(session, "tarot"):
        from .tarot.service import inject_overlay
        try:
            out = inject_overlay(character_id, out, mode=mode)
        except Exception as exc:
            print(f"[tarot] inject failed: {exc}")
    return out


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
    try:
        from .tarot.service import isolate_prompt
        if isolate_prompt(character_id, mode, user_text):
            return
    except Exception:
        pass
    if not (user_text or "").strip() or not (assistant_text or "").strip():
        return
    from .memory.worker import tick
    try:
        tick(character_id)
    except Exception as exc:
        print(f"[memory] extract tick failed: {exc}")
