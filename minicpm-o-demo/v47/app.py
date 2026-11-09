"""MiniCPM-V 4.7 1B 录屏看画面。只听 127.0.0.1。"""
from __future__ import annotations

import json
import queue
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

import engine

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="MiniCPM-V 4.7 1B Screen")
# 不挂整目录静态路由，页面只有一个 index。


class StartBody(BaseModel):
    scene: str = "auto"
    capture_fps: int = 1
    window_seconds: float = 4
    monitor: int = 1
    prompt: str = ""
    min_gap: float = 0
    max_new_tokens: int = 32
    max_edge: int = 960
    downsample: str = "16x"
    max_slice_nums: int = 1
    compare_prev: bool = True


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def api_status():
    return engine.status()


@app.get("/api/observations")
def api_observations(limit: int = 10):
    from observations import info, recent

    return {"log": info(), "observations": recent(limit)}


@app.post("/api/warmup")
def api_warmup():
    try:
        return {"ok": True, **engine.load()}
    except Exception as exc:
        return {"ok": False, "message": str(exc), **engine.status()}


@app.post("/api/start")
def api_start(body: StartBody):
    return engine.start_watch(body.model_dump())


@app.post("/api/stop")
def api_stop():
    from companion_video import close
    close()
    return engine.stop_watch()


class UpdateWatchBody(BaseModel):
    scene: str | None = None
    prompt: str | None = None
    compare_prev: bool | None = None
    max_new_tokens: int | None = None


@app.patch("/api/watch")
def api_update_watch(body: UpdateWatchBody):
    return engine.update_watch(body.model_dump())


class GlanceBody(BaseModel):
    scene: str = "auto"
    monitor: int = 1
    ask: str = ""
    along: bool = False
    before: str = ""
    gate: bool = False
    detail: bool = False
    crop: list[int] = []
    prompt: str = ""
    frames: int = 0
    window_hwnd: int = 0
    reaction: bool = False


@app.post("/api/video/observe")
def api_video_observe(body: GlanceBody):
    from companion_video import observe
    try:
        return observe(engine, body)
    except Exception as exc:
        return {"ok": False, "text": "", "message": str(exc)}


class ReactBody(BaseModel):
    prompt: str


@app.post("/api/video/react")
def api_video_react(body: ReactBody):
    from companion_video import react
    try:
        return react(engine, body)
    except Exception as exc:
        return {"ok": False, "text": "", "message": str(exc)}


@app.post("/api/video/stop")
def api_video_stop():
    from companion_video import request_close
    request_close()
    return {"ok": True}


@app.post("/api/glance")
def api_glance(body: GlanceBody):
    """看一帧，或陪看这几秒。给小可爱的 watch 技能用。"""
    try:
        return engine.glance_once(
            body.monitor, body.ask, body.along, body.before, body.gate,
            detail=body.detail, crop=body.crop, prompt=body.prompt, frames=body.frames, window_hwnd=body.window_hwnd,
        )
    except Exception as exc:
        return {"ok": False, "text": "", "message": str(exc)}


@app.post("/api/frames")
def api_frames(body: GlanceBody):
    """只交这几秒的原图。模型由小可爱按设置另调，不在这里加载。"""
    try:
        return engine.glance_once(
            body.monitor, body.ask, body.along, body.before, body.gate, infer=False,
            detail=body.detail, crop=body.crop, prompt=body.prompt, frames=body.frames, window_hwnd=body.window_hwnd,
        )
    except Exception as exc:
        return {"ok": False, "text": "", "images": [], "message": str(exc)}


def _sse(ev: dict) -> str:
    return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"


@app.get("/api/events")
def api_events():
    q = engine.subscribe()

    def gen():
        try:
            yield _sse({"type": "hello"})
            while True:
                try:
                    ev = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield _sse(ev)
        finally:
            engine.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8766, reload=False)
