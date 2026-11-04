"""角色卡导出：内部卡 → SillyTavern v2 PNG 卡。

优先回写：卡是从酒馆导入的（source_card 非空）就按原 JSON 结构更新已知字段，
未知字段（extensions、post_history_instructions 等）原样保留。
全新角色则按 v2 规格新建。PNG 用头像做底（无头像生成占位图），
元数据 key=chara，value=base64(utf-8 json)——和酒馆生态一致。
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any, Dict

from ...paths import AVATARS_DIR
from .card import (
    normalize_name, parse_greetings, parse_lorebook, parse_tags,
)

SOFTWARE = "xiaokeai"


def card_json_from_character(char: Any) -> Dict[str, Any]:
    """组装 v2 卡 JSON（含 spec 外壳）。"""
    entries = parse_lorebook(getattr(char, "lorebook", "") or "")
    greetings = parse_greetings(getattr(char, "greetings", "") or "")
    tags = parse_tags(getattr(char, "tags", "") or "")
    first_mes = (getattr(char, "greeting", "") or "").strip() or (greetings[0] if greetings else "")
    alternates = [g for g in greetings if g.strip() and g != first_mes]

    data_updates: Dict[str, Any] = {
        "name": getattr(char, "name", "") or "",
        "description": getattr(char, "persona", "") or "",
        "personality": getattr(char, "personality", "") or "",
        "scenario": getattr(char, "scenario", "") or "",
        "first_mes": first_mes,
        "mes_example": getattr(char, "mes_example", "") or "",
        "alternate_greetings": alternates,
        "character_book": {"entries": [e.to_dict() for e in entries]},
        "tags": tags,
        "creator": getattr(char, "creator", "") or "",
        "character_version": getattr(char, "card_version", "") or "",
    }

    raw_str = getattr(char, "source_card", "") or ""
    try:
        raw = json.loads(raw_str) if raw_str.strip() else None
    except (json.JSONDecodeError, TypeError):
        raw = None
    if isinstance(raw, dict) and str(raw.get("spec") or "").startswith("chara_card_v"):
        body = raw.get("data")
        if not isinstance(body, dict):
            body = {}
        # 内部条目是归一化格式，导出时把 position 转回 v2 枚举、键名对齐酒馆
        book = data_updates.pop("character_book")
        body.update(data_updates)
        body["character_book"] = {
            "entries": [_to_tavern_entry(e) for e in book["entries"]],
        }
        raw["data"] = body
        return raw
    return {
        "spec": "chara_card_v2",
        "data": {
            **data_updates,
            "character_book": {"entries": [_to_tavern_entry(e.to_dict()) for e in entries]},
        },
    }


def _to_tavern_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    pos = entry.get("position")
    pos_int = 2 if pos == "after_char" else (1 if pos == "before_hist" else 0)
    return {
        "keys": entry.get("keys") or [],
        "content": entry.get("content") or "",
        "enabled": bool(entry.get("enabled", True)),
        "constant": bool(entry.get("constant")),
        "selective": bool(entry.get("selective")),
        "keysecondary": entry.get("selective_keys") or [],
        "insertion_order": int(entry.get("order") or 100),
        "position": pos_int,
        "comment": entry.get("comment") or "",
        "case_sensitive": bool(entry.get("case_sensitive")),
        "prevent_recursion": bool(entry.get("prevent_recursion")),
        "exclude_recursion": bool(entry.get("exclude_recursion")),
    }


def export_png_bytes(char: Any) -> bytes:
    card = card_json_from_character(char)
    payload = base64.b64encode(
        json.dumps(card, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    from PIL import Image, PngImagePlugin

    img = _load_avatar(char) or _placeholder(char)
    info = PngImagePlugin.PngInfo()
    info.add_text("chara", payload)
    info.add_text("software", SOFTWARE)
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=info)
    return buf.getvalue()


def _load_avatar(char: Any) -> "Image.Image | None":
    rel = (getattr(char, "avatar_path", "") or "").strip()
    if not rel:
        return None
    from PIL import Image

    fp = (AVATARS_DIR / Path(rel).name).resolve()
    try:
        fp.relative_to(AVATARS_DIR.resolve())
    except ValueError:
        return None
    if not fp.is_file():
        return None
    try:
        with Image.open(fp) as im:
            im.load()
            return im.convert("RGB")
    except Exception:
        return None


def _placeholder(char: Any) -> "Image.Image":
    """无头像时生成 2:3 占位卡，颜色由名字哈希决定，肉眼可区分。"""
    from PIL import Image

    name = (getattr(char, "name", "") or "xiaoke").encode("utf-8")
    hue = int.from_bytes(name[:4].ljust(4, b"\0"), "big")
    r = 40 + (hue & 0x7F)
    g = 40 + ((hue >> 7) & 0x7F)
    b = 60 + ((hue >> 14) & 0x7F)
    return Image.new("RGB", (512, 768), (r, g, b))


def export_filename(char: Any) -> str:
    return normalize_name(getattr(char, "name", "") or "character") + ".png"
