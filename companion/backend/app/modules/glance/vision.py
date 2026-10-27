"""陪看的视觉模型。截屏仍是眼睛进程，模型调用按设置分开。

默认走本机 MiniCPM。换成 OpenAI 兼容接口时，眼睛只交原图，
这里像调用聊天模型一样把图发给另一个视觉模型。像素不进对话。
"""
from __future__ import annotations

import os
from typing import Any

from ...services.llm import auth_headers

FACT_PROMPT = (
    "这几张是前台窗口里的原图，按时间从早到晚。只写这块画面上看得见的事实。"
    "不要写用户的心情，不要把画面里的人物写成用户本人。"
    "画面中间若站着动漫角色，那是旁边的人，不要写她。"
    "看不清的名字留空，不要编。标题没变也要写眼前新发生的动作或原文。"
    "没有新的动作、原文或标题，只写没变。\n"
    "界面：\n窗口：\n类型：movie、music、video、code、slides、game、other、unknown 里选一个\n"
    "标题：\n歌手：音乐才写，没有就空着\n版本：没有就空着\n"
    "阶段：代码或幻灯片才写\n画面：屏幕里发生的事，一句\n"
    "原文：能读到的一行，没有就空着\n变化：这一眼新出现的屏幕事实，没有就写没变"
)


def vision_config() -> dict[str, Any]:
    conf = {
        "provider": "minicpm",
        "base_url": "",
        "api_key": "",
        "model": "",
    }
    try:
        from sqlmodel import Session

        from ...db import engine
        from ...services.settings_store import get_all

        with Session(engine) as session:
            stored = dict((get_all(session).get("vision") or {}))
        conf.update({key: stored.get(key) or conf[key] for key in conf})
    except Exception:
        pass
    provider = (os.environ.get("XIAOKE_VISION_PROVIDER") or "").strip()
    base = (os.environ.get("XIAOKE_VISION_BASE_URL") or "").strip()
    key = (os.environ.get("XIAOKE_VISION_API_KEY") or "").strip()
    model = (os.environ.get("XIAOKE_VISION_MODEL") or "").strip()
    if provider:
        conf["provider"] = provider
    if base:
        conf["base_url"] = base
    if key:
        conf["api_key"] = key
    if model:
        conf["model"] = model
    conf["provider"] = "minicpm" if (conf.get("provider") or "minicpm") == "minicpm" else "openai"
    return conf


def uses_local(conf: dict[str, Any] | None = None) -> bool:
    current = conf if conf is not None else vision_config()
    return (current.get("provider") or "minicpm") == "minicpm"


def build_payload(conf: dict[str, Any], prompt: str, images: list[str]) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image in images:
        raw = (image or "").strip()
        if not raw:
            continue
        url = raw if raw.startswith("data:") else f"data:image/jpeg;base64,{raw}"
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return {
        "model": conf.get("model") or "gpt-4o-mini",
        "messages": [{"role": "user", "content": parts}],
        "temperature": 0.2,
        "max_tokens": 240,
    }


def parse_completion(data: dict[str, Any]) -> str:
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return ""
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        texts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
        return "\n".join(part for part in texts if part).strip()
    return str(content or "").strip()


def _prompt(ask: str, before: str, gate: bool) -> str:
    if (ask or "").strip() and not gate:
        return (ask or "").strip()
    text = FACT_PROMPT
    earlier = (before or "").strip()
    if earlier:
        text += "\n已经记下的屏幕事实：\n" + earlier[:500] + "\n只写新的屏幕事实。没有新事实就只写没变。"
    return text


def complete(conf: dict[str, Any], prompt: str, images: list[str], timeout: float) -> dict[str, Any]:
    import httpx

    base = (conf.get("base_url") or "").rstrip("/")
    key = conf.get("api_key") or ""
    if not base or not key:
        return {"ok": False, "text": "", "message": "未配置视觉模型的地址或 Key"}
    if not images:
        return {"ok": False, "text": "", "message": "没有画面可送给视觉模型"}
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers=auth_headers(base, key),
            json=build_payload(conf, prompt, images),
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {"ok": False, "text": "", "message": str(exc)}
    if not isinstance(data, dict):
        return {"ok": False, "text": "", "message": "视觉模型没有返回"}
    return {"ok": True, "text": parse_completion(data)}


def describe(captured: dict[str, Any], *, ask: str, before: str, gate: bool, timeout: float) -> dict[str, Any]:
    """眼睛已经交来原图。这里只调用选中的视觉模型，并丢掉像素。"""
    conf = vision_config()
    images = list(captured.get("images") or [])
    found = complete(conf, _prompt(ask, before, gate), images, timeout)
    out = {key: value for key, value in captured.items() if key != "images"}
    out["provider"] = "openai"
    out["model"] = conf.get("model") or ""
    if not found.get("ok"):
        out["ok"] = False
        out["text"] = ""
        out["message"] = found.get("message") or "视觉模型没有看完"
        return out
    out["ok"] = True
    out["text"] = found.get("text") or ""
    return out
