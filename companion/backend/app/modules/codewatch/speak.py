"""Code 伴侣开口：坐在旁边看一眼，短、像她自己在说话。"""
from __future__ import annotations

from typing import Any, Dict, List

from .sources import label_of


def _hint_locale(phase: str, *, title: str, source: str, pack: Dict[str, Any]) -> str:
    task = (title or "").strip()
    clip = int(pack.get("clip_chars") or 48)
    bit = "".join(task.split())[:clip]
    desk = label_of(source)
    if phase == "started":
        about = str(pack.get("started_about_task") or "").format(desk=desk, task=task) if task else str(pack.get("started_about") or "").format(desk=desk)
        body = str(pack.get("started_body") or "")
        return f"{about}\n{body}".strip()
    if phase == "done":
        about = str(pack.get("done_about") or "").format(desk=desk)
        if bit:
            about += str(pack.get("done_bit") or "").format(bit=bit)
        body = str(pack.get("done_body") or "")
        return f"{about}\n{body}".strip()
    return ""


def hint(phase: str, *, title: str = "", tools: List[str] | None = None,
         project: str = "", source: str = "") -> str:
    from ...locale_pack import current_reply, prompts
    if current_reply() != "zh-CN":
        return _hint_locale(phase, title=title, source=source, pack=prompts().get("codewatch") or {})
    task = (title or "").strip() or ""
    bit = "".join(task.split())[:10]
    desk = label_of(source)
    if phase == "started":
        about = f"他刚在 {desk} 里动笔，大概是：{task}" if task else f"他刚在 {desk} 里动笔。"
        return (
            f"{about}\n"
            "你坐在旁边，用她自己平时的口吻接一句（最多 16 个字）。\n"
            "像回头看了一眼，轻、软、贴着人。说人话，不要报状态。\n"
            "口吻可以像：「又动笔了呀」「这回写这个？」「嗯，你开始了」。\n"
            "禁止：「开工了」「我看着」「我盯着」「开始工作」「收到」「好的」。\n"
            "禁止问要不要帮忙、列步骤、复述全文、客服腔。\n"
            "表演标记只要：[emo:happy][cam:half]\n"
            "不要旁白，不要 [dance:]。"
        )
    if phase == "done":
        about = f"{desk} 这轮停手了。"
        if bit:
            about += f"大概做的是：{bit}。"
        return (
            f"{about}\n"
            "你坐在旁边，用她自己平时的口吻收一句（最多 14 个字）。\n"
            "像看见他放下手，轻轻点一下就停。不要验收，不要总结。\n"
            "口吻可以像：「先这样吧」「这轮歇了？」「嗯，放下了」。\n"
            "禁止：「完成了」「交差了」「写完了」「好了这轮」「结束了」「总结如下」。\n"
            "禁止问还要不要改、列步骤、客服腔。\n"
            "表演标记只要：[emo:relaxed][cam:half]\n"
            "不要旁白，不要 [dance:]。"
        )
    return ""


def from_request(extra: Dict[str, Any]) -> str:
    phase = str(extra.get("codewatch_phase") or "").strip()
    raw_tools = extra.get("codewatch_tools")
    tools: List[str] = []
    if isinstance(raw_tools, list):
        tools = [str(x).strip() for x in raw_tools if str(x).strip()]
    elif isinstance(raw_tools, str) and raw_tools.strip():
        tools = [p.strip() for p in raw_tools.split(",") if p.strip()]
    return hint(
        phase,
        title=str(extra.get("codewatch_title") or ""),
        tools=tools,
        project=str(extra.get("codewatch_project") or ""),
        source=str(extra.get("codewatch_source") or ""),
    )
