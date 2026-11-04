"""SillyTavern / AICC 角色卡导入：PNG 元数据 / 纯 JSON，多规格统一映射到内部卡。

PNG 卡的数据在文本块里，可能的 key：
- chara   酒馆 v1/v2，base64(utf-8 json)
- ccv3    酒馆 v3，base64(utf-8 json)
- aiCdv1:* / 站点自定义 key  aicharactercards.com 新版用 aicc_card 规格，仍写 chara

注意 PIL 只读 IDAT 之前的文本块，写卡在图像数据后追加元数据是常态，
所以这里自己扫 PNG chunk（tEXt / zTXt / iTXt 全量），不依赖 img.info。

内部只有一套角色卡格式（models.Character），这里只做视图映射；
原始 JSON 存进 source_card，导出时按原结构回写、未知字段不丢。
"""
from __future__ import annotations

import base64
import json
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .card import LorebookEntry, dump_lorebook, normalize_name

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_CARD_BYTES = 20 * 1024 * 1024  # 角色卡 PNG 一般几百 KB，20MB 封顶防误传


class CardParseError(ValueError):
    pass


@dataclass
class ParsedCard:
    name: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    alternate_greetings: List[str] = field(default_factory=list)
    lorebook: List[LorebookEntry] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    creator: str = ""
    card_version: str = ""
    source_format: str = "native"   # native | tavern_v1 | tavern_v2 | tavern_v3 | aicc
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PNG 文本块解析（PIL 漏 IDAT 后的块，必须自己扫）
# ---------------------------------------------------------------------------

def _decode_text_value(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", "replace")


def _load_png_text(data: bytes) -> Dict[str, str]:
    """扫全 PNG chunk，收集 tEXt / zTXt / iTXt（键 -> 文本值）。"""
    if data[:8] != PNG_MAGIC:
        raise CardParseError("不是 PNG 文件")
    out: Dict[str, str] = {}
    pos = 8
    n = len(data)
    while pos + 8 <= n:
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        if len(body) < ln:
            break
        if typ == b"tEXt":
            key, _, val = body.partition(b"\x00")
            if key:
                out[key.decode("latin-1", "replace")] = _decode_text_value(val)
        elif typ == b"zTXt":
            key, _, rest = body.partition(b"\x00")
            if key and rest:
                try:
                    out[key.decode("latin-1", "replace")] = _decode_text_value(
                        zlib.decompress(rest[1:]))
                except Exception:
                    pass
        elif typ == b"iTXt":
            parts = body.split(b"\x00", 2)
            if len(parts) >= 3:
                key = parts[0]
                flag_method = parts[1]
                tail = parts[2]
                # tail: lang\0translated\0text
                idx = [i for i, b in enumerate(tail) if b == 0]
                if len(idx) >= 2:
                    text = tail[idx[1] + 1:]
                    if flag_method[:1] == b"\x01":
                        try:
                            text = zlib.decompress(text)
                        except Exception:
                            continue
                    out[key.decode("latin-1", "replace")] = _decode_text_value(text)
        pos += 12 + ln
    return out


def _card_from_png(data: bytes) -> Dict[str, Any]:
    info = _load_png_text(data)
    # chara 优先（v1/v2 与 aicc 都写它），ccv3 次之
    for key in ("chara", "ccv3"):
        blob = (info.get(key) or "").strip()
        if not blob:
            continue
        try:
            text = base64.b64decode(blob).decode("utf-8")
            card = json.loads(text)
        except Exception as exc:
            raise CardParseError(f"PNG 元数据 {key} 不是合法角色卡 JSON：{exc}") from exc
        if isinstance(card, dict):
            card.setdefault("spec", "chara_card_v3" if key == "ccv3" else "chara_card_v2")
            return card
    raise CardParseError("PNG 里没有找到角色卡数据（缺 chara/ccv3 元数据）")


def _extract_json(data: bytes, filename: str) -> Dict[str, Any]:
    """PNG 走元数据，其余按纯 JSON 文本认。判型看魔数，扩展名只是兜底。"""
    if data[:8] == PNG_MAGIC:
        return _card_from_png(data)
    try:
        card = json.loads(data.decode("utf-8-sig"))
    except Exception as json_exc:
        if (filename or "").lower().endswith(".png"):
            return _card_from_png(data)
        raise CardParseError(f"不是合法的 JSON 角色卡：{json_exc}") from json_exc
    if not isinstance(card, dict):
        raise CardParseError("角色卡 JSON 顶层必须是对象")
    return card


# ---------------------------------------------------------------------------
# 各规格统一映射
# ---------------------------------------------------------------------------

def _norm_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return []


def _macro(text: str, name: str) -> str:
    """{{char}}/{{user}} 宏替换：导入即落到我们的称呼口径。"""
    if not text:
        return text
    return (text
            .replace("{{char}}", name).replace("{{Char}}", name)
            .replace("{{user}}", "对方").replace("{{User}}", "对方"))


def _parse_tavern(body: Dict[str, Any], source_format: str) -> ParsedCard:
    name = str(body.get("name") or "").strip()
    if not name:
        raise CardParseError("角色卡没有 name 字段")
    description = str(body.get("description") or "")
    # system_prompt 是追加给模型的指令块（v2/v3 都有），并入 description 一体保存
    sys_prompt = str(body.get("system_prompt") or "").strip()
    if sys_prompt:
        description = (description + "\n\n" + sys_prompt).strip()

    mes_example = _strip_start_markers(str(body.get("mes_example") or ""))
    # post_history_instructions / depth_prompt 酒馆按深度插在历史里，
    # 我们 import 时近似拼进对话示例列；原始 JSON 在 source_card 里不丢
    post = str(body.get("post_history_instructions") or "").strip()
    if post:
        mes_example = (mes_example + "\n---\n" + post).strip() if mes_example else post
    depth_prompt = body.get("depth_prompt")
    if isinstance(depth_prompt, dict):
        dp = str(depth_prompt.get("prompt") or "").strip()
        if dp:
            mes_example = (mes_example + "\n---\n" + dp).strip() if mes_example else dp

    book_raw = body.get("character_book") or {}
    entries_raw: List[Any] = []
    if isinstance(book_raw, dict):
        entries_raw = list(book_raw.get("entries") or [])
    elif isinstance(book_raw, list):
        entries_raw = book_raw

    return ParsedCard(
        name=normalize_name(name),
        description=description,
        personality=str(body.get("personality") or ""),
        scenario=str(body.get("scenario") or ""),
        first_mes=str(body.get("first_mes") or ""),
        mes_example=mes_example,
        alternate_greetings=_norm_str_list(body.get("alternate_greetings")),
        lorebook=[LorebookEntry.from_dict(e) for e in entries_raw if isinstance(e, dict)],
        tags=_norm_str_list(body.get("tags") or body.get("tag_list")),
        creator=str(body.get("creator") or body.get("author") or ""),
        card_version=str(body.get("character_version") or body.get("version") or ""),
        source_format=source_format,
    )


def _strip_start_markers(text: str) -> str:
    """<START> 是酒馆示例对话的分隔标记，不是内容本身，导入时剥掉。"""
    if not text:
        return text
    return "\n".join(line for line in text.split("\n") if line.strip() != "<START>").strip()


def _flatten_style(style: Any) -> str:
    """speech_style 可能是 dict：压平成 key: value 行。"""
    if isinstance(style, str):
        return style.strip()
    if isinstance(style, dict):
        lines = []
        for k, v in style.items():
            if isinstance(v, (str, int, float)):
                lines.append(f"{k}: {v}")
            elif isinstance(v, list):
                lines.append(f"{k}: " + "、".join(str(x) for x in v))
        return "\n".join(lines)
    return ""


def _parse_aicc(body: Dict[str, Any]) -> ParsedCard:
    """aicharactercards.com 的 aicc_card 1.0 规格。"""
    name = str(body.get("name") or "").strip()
    if not name:
        raise CardParseError("角色卡没有 name 字段")

    persona_parts = [str(body.get("general_description") or "").strip()]
    appearance = str(body.get("appearance") or "").strip()
    if appearance:
        persona_parts.append(f"# 外貌\n{appearance}")
    description = "\n\n".join(p for p in persona_parts if p)

    personality = (body.get("personality") or {})
    if not isinstance(personality, dict):
        personality = {"core": str(personality or "")}
    p_lines = [str(personality.get("core") or "").strip()]
    for rule in _norm_str_list(personality.get("behavior_rules")):
        p_lines.append(f"- {rule}")
    style = _flatten_style(personality.get("speech_style"))
    if style:
        p_lines.append(style)
    personality_text = "\n".join(p for p in p_lines if p)

    scenario_parts = [
        str(body.get("background_history") or "").strip(),
        str(body.get("world_setting_context") or "").strip(),
    ]
    scenario = "\n\n".join(p for p in scenario_parts if p)

    dialogue = body.get("dialogue") or {}
    greetings = [str(g) for g in _norm_str_list(dialogue.get("greetings"))]
    examples = [str(e) for e in _norm_str_list(dialogue.get("dialogue_examples"))]
    mes_example = _strip_start_markers("\n---\n".join(examples))

    prompts = body.get("prompts") or {}
    if isinstance(prompts, dict):
        sys_prompt = str(prompts.get("system_prompt") or "").strip()
        if sys_prompt:
            description = (description + "\n\n" + sys_prompt).strip()
        post = str(prompts.get("post_history_instructions") or "").strip()
        if post:
            mes_example = (mes_example + "\n---\n" + post).strip() if mes_example else post

    world = body.get("world") or {}
    entries_raw = world.get("worldbook_entries") or []
    entries: List[LorebookEntry] = []
    if isinstance(entries_raw, list):
        for e in entries_raw:
            if not isinstance(e, dict):
                continue
            ext = e.get("extensions") or {}
            if not isinstance(ext, dict):
                ext = {}
            selective_keys = _norm_str_list(e.get("secondary_keys"))
            entries.append(LorebookEntry.from_dict({
                "keys": e.get("keys"),
                "content": e.get("content"),
                "constant": e.get("constant"),
                "selective": bool(e.get("selective")) or bool(selective_keys),
                "selective_keys": selective_keys,
                "order": e.get("order") or ext.get("insertion_order") or ext.get("priority"),
                "position": e.get("position", ext.get("position", "before_char")),
                "enabled": e.get("enabled", True),
                "comment": e.get("comment") or e.get("name") or "",
            }))

    meta = body.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    return ParsedCard(
        name=normalize_name(name),
        description=description,
        personality=personality_text,
        scenario=scenario,
        first_mes=greetings[0] if greetings else "",
        mes_example=mes_example,
        alternate_greetings=greetings[1:],
        lorebook=entries,
        tags=_norm_str_list(meta.get("tags")),
        creator=str(meta.get("creator") or ""),
        card_version=str(meta.get("version") or ""),
        source_format="aicc",
    )


def parse_card(data: bytes, filename: str = "") -> ParsedCard:
    if not data or len(data) > MAX_CARD_BYTES:
        raise CardParseError("文件为空或超过 20MB 上限")
    raw = _extract_json(data, filename)
    spec = str(raw.get("spec") or "").strip()
    body: Dict[str, Any]
    if spec == "chara_card_v3":
        source_format = "tavern_v3"
        body = raw.get("data") or {}
    elif spec == "chara_card_v2":
        source_format = "tavern_v2"
        body = raw.get("data") or {}
    elif spec == "aicc_card":
        source_format = "aicc"
        body = raw.get("data") or {}
    elif spec:
        raise CardParseError(f"不支持的角色卡规格：{spec}")
    else:
        # v1：字段在顶层，没有 spec 标记
        source_format = "tavern_v1"
        body = raw

    if not isinstance(body, dict):
        raise CardParseError("角色卡 data 字段不是对象")

    if source_format == "aicc":
        card = _parse_aicc(body)
    else:
        card = _parse_tavern(body, source_format)
    card.raw = raw
    # 宏替换：让卡开箱就能用我们的称呼口径
    n = card.name
    card.description = _macro(card.description, n)
    card.personality = _macro(card.personality, n)
    card.scenario = _macro(card.scenario, n)
    card.first_mes = _macro(card.first_mes, n)
    card.mes_example = _macro(card.mes_example, n)
    card.alternate_greetings = [_macro(g, n) for g in card.alternate_greetings]
    for e in card.lorebook:
        e.content = _macro(e.content, n)
        e.comment = _macro(e.comment, n)
    return card


def card_to_character_fields(card: ParsedCard) -> Dict[str, Any]:
    """映射成 Character 列值（ORM 由路由侧组装）。"""
    greetings = [card.first_mes] if card.first_mes.strip() else []
    for g in card.alternate_greetings:
        if g.strip() and g not in greetings:
            greetings.append(g)
    return {
        "name": card.name,
        "persona": card.description,
        "personality": card.personality,
        "scenario": card.scenario,
        "mes_example": card.mes_example,
        "greeting": card.first_mes,
        "greetings": json.dumps(greetings, ensure_ascii=False),
        "lorebook": dump_lorebook(card.lorebook),
        "tags": json.dumps(card.tags, ensure_ascii=False),
        "creator": card.creator,
        "card_version": card.card_version,
        "source_format": card.source_format,
        "source_card": json.dumps(card.raw, ensure_ascii=False),
    }
