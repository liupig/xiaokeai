"""被碰一下时的那句：沿用现有表演，不另开说话系统。"""
from __future__ import annotations


_ZH = (
    "这是被碰了一下，不是新话题。\n"
    "只说一句很短的口语，最多 14 个字，接上面写的位置和态度。态度不要改。\n"
    "态度是躲开、护住、腻了、冷淡时，把人推开，不要邀请继续摸。\n"
    "态度是亲昵、害羞、闹着玩时，也只轻轻接一句，不要展开，不要问问题。\n"
    "表演只用 [emo:]，可以再加一个 [intent:look] 或 [intent:nod] 或 [intent:shy]。\n"
    "禁止 [dance:] [act:]，禁止旁白，禁止换话题，禁止追问。"
)


def hint_for(text: str) -> str:
    from ...locale_pack import prompts
    body = str((prompts().get("touch") or {}).get("body") or "") or _ZH
    fact = (text or "").strip()
    return f"{fact}\n{body}".strip() if fact else body
