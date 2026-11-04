"""角色卡 v2 公共结构：统一卡是 SillyTavern 卡的超集，酒馆卡只是导入/导出视图。

内部只有一套格式（models.Character 的列），导入时把 v1/v2/v3 映射进来，
导出时按 v2 规格写回；source_card 保留原始 JSON，未知字段不丢。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 世界书注入位置（对齐酒馆/AICC 的 position 写法，两种类型都收）
# 工程语义：before_char=紧跟人设层 | after_char=红线+用户档案之后
#          | before_hist=历史之前（贴近对话）
POSITIONS = {"before_char", "after_char", "before_hist"}
_POSITION_INT = {0: "before_char", 1: "before_hist", 2: "after_char"}


@dataclass
class LorebookEntry:
    keys: List[str] = field(default_factory=list)
    content: str = ""
    constant: bool = False            # 常驻：每轮都注入
    selective: bool = False           # 选择性：secondary 键也要命中才注入
    selective_keys: List[str] = field(default_factory=list)
    order: int = 100                  # 注入顺序，小的在前
    position: str = "before_char"     # before_char=紧跟人设 | before_hist=历史之前
    enabled: bool = True
    comment: str = ""                 # 条目标题，仅编辑器展示
    case_sensitive: bool = False      # 关键词大小写敏感
    prevent_recursion: bool = False   # 不被递归扫描触发
    exclude_recursion: bool = False   # 注入后内容不参与下一轮触发

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LorebookEntry":
        keys = raw.get("keys") or []
        if isinstance(keys, str):
            keys = [k for k in re.split(r"[,\n]", keys) if k.strip()]
        sec = raw.get("selective_keys") or raw.get("keysecondary") or []
        if isinstance(sec, str):
            sec = [k for k in re.split(r"[,\n]", sec) if k.strip()]
        pos = raw.get("position", "before_char")
        if isinstance(pos, int):
            pos = _POSITION_INT.get(pos, "before_char")
        if pos not in POSITIONS:
            pos = "before_char"
        order = raw.get("order", raw.get("insertion_order", 100))
        try:
            order = int(order)
        except (TypeError, ValueError):
            order = 100
        return cls(
            keys=[str(k).strip() for k in keys if str(k).strip()],
            content=str(raw.get("content") or ""),
            constant=bool(raw.get("constant")),
            selective=bool(raw.get("selective")),
            selective_keys=[str(k).strip() for k in sec if str(k).strip()],
            order=order,
            position=pos,
            enabled=bool(raw.get("enabled", True)),
            comment=str(raw.get("comment") or raw.get("title") or ""),
            case_sensitive=bool(raw.get("case_sensitive")),
            prevent_recursion=bool(raw.get("prevent_recursion")),
            exclude_recursion=bool(raw.get("exclude_recursion")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keys": list(self.keys),
            "content": self.content,
            "constant": self.constant,
            "selective": self.selective,
            "selective_keys": list(self.selective_keys),
            "order": self.order,
            "position": self.position,
            "enabled": self.enabled,
            "comment": self.comment,
            "case_sensitive": self.case_sensitive,
            "prevent_recursion": self.prevent_recursion,
            "exclude_recursion": self.exclude_recursion,
        }


def parse_lorebook(raw: str) -> List[LorebookEntry]:
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [LorebookEntry.from_dict(e) for e in data if isinstance(e, dict)]


def dump_lorebook(entries: List[LorebookEntry]) -> str:
    return json.dumps([e.to_dict() for e in entries], ensure_ascii=False)


def _parse_str_list(raw: str) -> List[str]:
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if str(x).strip()]


def parse_greetings(raw: str) -> List[str]:
    return _parse_str_list(raw)


def parse_tags(raw: str) -> List[str]:
    return _parse_str_list(raw)


def compose_persona(char: Any) -> str:
    """拼送模型的人设主层：persona(=酒馆 description) 原样在前，
    personality / scenario / mes_example 作为小节附加，没填的不出现。"""
    parts: List[str] = [(getattr(char, "persona", "") or "").strip()]
    personality = (getattr(char, "personality", "") or "").strip()
    if personality:
        parts.append(f"# 性格\n{personality}")
    scenario = (getattr(char, "scenario", "") or "").strip()
    if scenario:
        parts.append(f"# 场景\n{scenario}")
    example = (getattr(char, "mes_example", "") or "").strip()
    if example:
        parts.append(f"# 对话示例\n{example}")
    return "\n\n".join(p for p in parts if p)


def compose_user_persona(conf_persona: Any) -> str:
    """设置里的「我的档案」拼成注入层。返回空串表示未启用。"""
    if not isinstance(conf_persona, dict):
        return ""
    if not conf_persona.get("enabled"):
        return ""
    desc = str(conf_persona.get("description") or "").strip()
    name = str(conf_persona.get("name") or "").strip()
    if not desc and not name:
        return ""
    head = f"和你说话的人叫{name}。" if name else "和你说话的人是下面这位。"
    return (
        f"{head}{desc}\n"
        "把他当成你已经熟悉的人：不用问他是谁、叫什么；"
        "没写到的事就当还不知道，照常聊天自然会熟起来。"
    )


LOREBOOK_HEADER = (
    "【世界书·设定补充】下面是和当前话题相关的背景设定，"
    "当作你本来就知道的事实来接话，不要逐条复述，不要提「设定」两个字："
)


def format_lorebook(contents: List[str]) -> str:
    return LOREBOOK_HEADER + "\n" + "\n".join(f"- {c}" for c in contents)


def normalize_name(name: str, fallback: str = "未命名") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name or "").strip()
    return cleaned or fallback
