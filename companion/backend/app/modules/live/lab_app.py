"""轻量彩排启动器；不运行正式启动扫描、预热、扣费账本或真实平台连接。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ...paths import WEB_DIR
from ...routers import assets, characters, settings, speech
from .lab_router import router, get_lab


@asynccontextmanager
async def lifespan(_app):
    yield
    get_lab().stop()


app = FastAPI(title="直播彩排", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Audio-Format", "X-Audio-Rate"])
for routes in (router, assets.router, characters.router, settings.router, speech.router):
    app.include_router(routes)


@app.get("/")
@app.get("/live-lab.html")
def page():
    return FileResponse(WEB_DIR / "live-lab.html", headers={"Cache-Control": "no-store"})


if (WEB_DIR / "static").is_dir():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


@app.get("/assets/{path:path}")
def asset(path: str):
    from ...paths import resolve_asset_file
    from fastapi import HTTPException
    result = resolve_asset_file(path)
    if result is None:
        raise HTTPException(404, "asset not found")
    return FileResponse(result)
