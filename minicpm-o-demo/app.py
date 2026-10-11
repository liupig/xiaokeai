"""MiniCPM-o 4.5 独立小 Demo。和 companion 不是同一个 Python。"""
from __future__ import annotations

import base64
import io
import json
from typing import Optional

import numpy as np
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from engine import IN_SR, infer, status, warmup

ROOT = __import__("pathlib").Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="MiniCPM-o 4.5 Demo")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def api_status():
    return status()


@app.post("/api/warmup")
def api_warmup(prefer: str = Query("auto")):
    try:
        return {"ok": True, **warmup(prefer)}
    except Exception as exc:
        return {"ok": False, "message": str(exc), **status()}


def _audio_from_upload(raw: bytes) -> np.ndarray:
    import librosa
    import soundfile as sf
    bio = io.BytesIO(raw)
    try:
        data, sr = sf.read(bio, dtype="float32")
    except Exception:
        bio.seek(0)
        # 浏览器可能丢 webm，退回原始 float32 pcm（小端）
        arr = np.frombuffer(raw, dtype="<f4")
        if arr.size == 0:
            raise
        return arr
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != IN_SR:
        data = librosa.resample(data, orig_sr=sr, target_sr=IN_SR)
    return np.asarray(data, dtype=np.float32)


@app.post("/api/turn")
async def api_turn(
    audio: Optional[UploadFile] = File(None),
    image: Optional[UploadFile] = File(None),
    pcm_b64: str = Form(""),
):
    raw = await audio.read() if audio is not None else b""
    if pcm_b64.strip():
        samples = np.frombuffer(base64.b64decode(pcm_b64), dtype="<f4")
    elif raw:
        samples = _audio_from_upload(raw)
    else:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': '没有音频'}, ensure_ascii=False)}\n\n"]),
            media_type="text/event-stream",
        )
    img = None
    if image is not None:
        blob = await image.read()
        if blob:
            from PIL import Image
            img = Image.open(io.BytesIO(blob)).convert("RGB")

    def sse():
        try:
            for ev in infer(samples, img):
                if ev.get("type") == "audio" and ev.get("pcm"):
                    ev = {
                        "type": "audio",
                        "rate": ev.get("rate") or 24000,
                        "pcm_b64": base64.b64encode(ev["pcm"]).decode("ascii"),
                    }
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8765, reload=False)
