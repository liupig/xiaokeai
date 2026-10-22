"""把 [draw:画面] 交给火山 Seedream，落成一张牌能贴的图。"""
from __future__ import annotations

import os
import re
import time
import uuid
import asyncio
from typing import Any, Dict

import httpx

from sqlmodel import Session

from ...db import engine
from ...models import Keepsake
from ...paths import KEEPSAKES_DIR
from ...services.duplex import make_unit

DRAW_MODEL = "doubao-seedream-5-0-pro-260628"
IMAGES_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
# 牌在屏幕上大约两百像素，放大也不过一千。1K 竖图比 2K 少一大块像素，出图会短一截。
_SIZES = ("1024x1536", "1K")
_FAIL = "这张没画出来。"
_ARRIVED = "好了，你看。"
_DRAW_BARE = re.compile(r"(?:再|还)?(?:画|来)一[张幅](?:画|图)?")
_DRAW_LEAD = re.compile(
    r"^(?:请)?(?:帮我画|给我画|画个图|画张图|画一幅图|画一张图|画一幅|画一张|画一副|画)[:：]?"
)
_LEAD_STRIP = re.compile(r"^(?:请)?(?:帮我画|给我画|画|出)(?:一[张幅个只])?")
_SCENE_LIMIT = 800
_NOT_A_DRAW = re.compile(r"^画[得的了完]")
_ASKED_SCENE = re.compile(r"画点什么|想画什么|画什么")
_NOT_A_SCENE = re.compile(r"^(?:好|嗯|哦|行|不要|算了|不用|再看看)+$")


def user_draw_scene(text: str, prior=None) -> str:
    """对方这句本身就是一幅具体的画。空字符串表示先别画，等她问清再画。"""
    original = re.sub(r"\s+", " ", (text or "").strip())
    compact = re.sub(r"\s+", "", original)
    if not compact or _DRAW_BARE.fullmatch(compact) or _NOT_A_DRAW.match(compact):
        return ""
    if _DRAW_LEAD.match(compact):
        scene = _DRAW_LEAD.sub("", original).strip(" ：:，。")
        scene = re.sub(r"\s+", " ", scene).strip()
        if len(re.sub(r"\s+", "", scene)) < 2:
            return ""
        return scene[:_SCENE_LIMIT]
    if len(compact) > 80:
        return ""
    rest = _LEAD_STRIP.sub("", compact)
    asked = _asked_for_a_scene(prior)
    if not rest or (rest == compact and not asked):
        return ""
    if rest == compact and (_NOT_A_SCENE.fullmatch(compact) or len(compact) > 24 or re.search(r"[吗?？]", compact)):
        return ""
    return original[:_SCENE_LIMIT]


def opening_line(scene: str) -> str:
    """画面已经从对方原话里定了，这句不等模型把整段写完。"""
    rest = _LEAD_STRIP.sub("", re.sub(r"\s+", "", scene or "")).strip("，。！？、：:")
    if not rest or re.search(r"[A-Za-z]", rest[:12]):
        return "好，我来画。"
    if len(rest) > 16:
        rest = rest[:16]
    return f"好，{rest}，我来画。"


def _asked_for_a_scene(prior) -> bool:
    for message in reversed(list(prior or [])):
        if (message.get("role") or "") != "assistant":
            continue
        return bool(_ASKED_SCENE.search(message.get("content") or ""))
    return False


def draw_key(llm_conf: Dict[str, Any], env: Dict[str, str] | None = None) -> str:
    """出图固定走火山。聊天地址是火山就用那把，否则只用 ARK_API_KEY。"""
    if env is None:
        from ...services.settings_store import _load_local_env

        _load_local_env()
        env = os.environ
    base = str((llm_conf or {}).get("base_url") or "")
    key = str((llm_conf or {}).get("api_key") or "").strip()
    if key and ("volces.com" in base or "volcengine.com" in base):
        return key
    return (env.get("ARK_API_KEY") or env.get("VOLC_ARK_API_KEY") or "").strip()


def _keep(character_id: int, raw: bytes, ext: str, caption: str, quote: str) -> str:
    """写入证物相册。文件名要过相册的校验，列表里才找得到。"""
    fname = f"{int(character_id)}_{uuid.uuid4().hex}{ext}"
    KEEPSAKES_DIR.mkdir(parents=True, exist_ok=True)
    (KEEPSAKES_DIR / fname).write_bytes(raw)
    mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
    with Session(engine) as session:
        session.add(Keepsake(
            character_id=int(character_id),
            kind="still",
            path=fname,
            mime=mime,
            caption=(caption or "")[:80],
            quote=(quote or "")[:120],
        ))
        session.commit()
    return f"/api/modules/keepsakes/file/{fname}"


def render_card(prompt: str, llm_conf: Dict[str, Any], character_id: int) -> Dict[str, str]:
    """同步出图。图落进证物相册，返回相册地址和短标题。"""
    key = draw_key(llm_conf)
    if not key:
        raise RuntimeError("没有绘图用的密钥")
    scene = re.sub(r"\s+", " ", re.sub(r"[\[\]]", "", prompt or "")).strip()[:_SCENE_LIMIT]
    if len(scene) < 2:
        raise RuntimeError("没有画面")
    payload_base = {
        "model": DRAW_MODEL,
        "prompt": f"{scene}。竖构图，主体清楚，画面里不要文字。",
        "response_format": "url",
        "watermark": False,
    }
    started = time.perf_counter()
    with httpx.Client(timeout=180.0, trust_env=False) as client:
        resp = None
        last_err = "出图失败"
        for size in _SIZES:
            body = dict(payload_base)
            body["size"] = size
            resp = client.post(
                IMAGES_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code < 400:
                break
            last_err = f"HTTP {resp.status_code}: {resp.text[:180]}"
            if resp.status_code != 400:
                raise RuntimeError(last_err)
            resp = None
        if resp is None:
            raise RuntimeError(last_err)
        items = (resp.json().get("data") or [])
        remote = (items[0].get("url") if items else "") or ""
        if not remote:
            raise RuntimeError("响应里没有图片")
        fetched = client.get(remote, follow_redirects=True)
        fetched.raise_for_status()
        raw = fetched.content
    ext = ".jpg" if raw[:2] == b"\xff\xd8" else ".png"
    title = scene[:10]
    url = _keep(character_id, raw, ext, title, scene)
    print(f"[draw] {url.rsplit('/', 1)[-1]} {time.perf_counter() - started:.0f}s")
    return {"url": url, "name": title}


async def realize_draws(
    events, llm_conf: Dict[str, Any], *, character_id: int = 0, allow: bool = True,
    user_text: str = "", prior=None,
):
    """对方原话已经能开画时，图和第一句同时走。嘴不用等模型把整段写完。"""
    early = user_draw_scene(user_text, prior) if allow else ""
    task = asyncio.create_task(_to_thread(render_card, early, llm_conf, character_id)) if early else None
    said = ""
    try:
        if early:
            yield {"type": "drawing", "name": early[:10]}
            said = opening_line(early)
            yield {"type": "text", "delta": said}
            yield make_unit(said, "phrase", "interrupt_or_queue")
        async for ev in events:
            if ev.get("type") == "done" and said and said not in str(ev.get("full_text") or ""):
                ev = {**ev, "full_text": said + str(ev.get("full_text") or "")}
            if ev.get("type") != "draw":
                yield ev
                continue
            if task is not None or not allow:
                continue
            yield {"type": "drawing", "name": str(ev.get("value") or "").strip()[:10]}
            try:
                info = await _to_thread(
                    render_card, str(ev.get("value") or ""), llm_conf, character_id,
                )
            except Exception as exc:
                err = str(exc).splitlines()[0][:180]
                print(f"[draw] fail {err}")
                yield {"type": "text", "delta": _FAIL}
                yield make_unit(_FAIL, "body", "queue")
                yield {"type": "picture", "url": "", "name": ""}
                continue
            yield {"type": "picture", "url": info["url"], "name": info["name"]}
            yield {"type": "text", "delta": _ARRIVED}
            yield make_unit(_ARRIVED, "body", "queue")
        if task is not None:
            try:
                info = await task
            except Exception as exc:
                err = str(exc).splitlines()[0][:180]
                print(f"[draw] fail {err}")
                yield {"type": "text", "delta": _FAIL}
                yield make_unit(_FAIL, "body", "queue")
                yield {"type": "picture", "url": "", "name": ""}
            else:
                yield {"type": "picture", "url": info["url"], "name": info["name"]}
                yield {"type": "text", "delta": _ARRIVED}
                yield make_unit(_ARRIVED, "body", "queue")
    finally:
        if task is not None and not task.done():
            task.cancel()
        close = getattr(events, "aclose", None)
        if close:
            try:
                await close()
            except Exception:
                pass


async def _to_thread(fn, *args):
    import asyncio
    return await asyncio.to_thread(fn, *args)
