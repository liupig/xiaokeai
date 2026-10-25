"""模块开关：从 settings.modules 读取，缺省视为开启。"""
from typing import Dict

from sqlmodel import Session

from ..services import settings_store

MODULE_KEYS = ("memory", "scenes", "rewrite", "keepsake", "tarot", "codewatch", "touch", "harness", "glance")
# 缺省都开。dsh 内核在 requirements 里，克隆后装环境就能用。
# glance 默认关：不开就不截屏，也不把「看一眼」写进技能目录。
_DEFAULT_OFF = frozenset({"glance"})


def all_flags(session: Session) -> Dict[str, bool]:
    raw = settings_store.get_all(session).get("modules") or {}
    return {k: bool(raw.get(k, k not in _DEFAULT_OFF)) for k in MODULE_KEYS}


def enabled(session: Session, name: str) -> bool:
    return all_flags(session).get(name, True)
