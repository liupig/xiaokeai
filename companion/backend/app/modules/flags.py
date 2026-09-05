"""模块开关：从 settings.modules 读取，缺省视为开启。"""
from typing import Dict

from sqlmodel import Session

from ..services import settings_store

MODULE_KEYS = ("memory", "scenes", "rewrite", "keepsake", "tarot", "codewatch")


def all_flags(session: Session) -> Dict[str, bool]:
    raw = settings_store.get_all(session).get("modules") or {}
    return {k: bool(raw.get(k, True)) for k in MODULE_KEYS}


def enabled(session: Session, name: str) -> bool:
    return all_flags(session).get(name, True)
