"""开播之后，陪看不再把屏幕上的片子说出去。"""
from __future__ import annotations


def blocks_glance() -> bool:
    try:
        from .config import feature_on
        from .host import host

        if not host.on_air:
            return False
        return feature_on(host.cfg(), "content_gate")
    except Exception:
        return False
