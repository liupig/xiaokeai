"""打包版前端入口：页面和 3D 资产本地提供，只把 /api 转到后端。"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope


class _AssetFiles(StaticFiles):
    """PMX 贴图路径常带反斜杠；浏览器请求时统一成 /。"""

    async def get_response(self, path: str, scope: Scope):
        return await super().get_response((path or "").replace("\\", "/"), scope)

from .paths import ASSETS_DIR, KEEPSAKES_DIR, WEB_DIR

BACKEND = os.environ.get("COMPANION_BACKEND", "http://127.0.0.1:9610").rstrip("/")
_HOP = {"host", "content-length", "transfer-encoding", "connection", "keep-alive"}

app = FastAPI(title="Companion Studio Web", version="0.1.0")
_client = httpx.AsyncClient(
    base_url=BACKEND,
    timeout=httpx.Timeout(600.0, connect=15.0),
    limits=httpx.Limits(max_connections=40, max_keepalive_connections=10),
)


async def _proxy(request: Request) -> StreamingResponse:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    body = await request.body()
    req = _client.build_request(request.method, target, headers=headers, content=body or None)
    resp = await _client.send(req, stream=True)
    out = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in _HOP | {"content-encoding"}
    }
    async def gen():
        try:
            async for chunk in resp.aiter_bytes(4096):
                yield chunk
        finally:
            await resp.aclose()

    return StreamingResponse(
        gen(),
        status_code=resp.status_code,
        headers=out,
    )


_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


@app.api_route("/api", methods=_METHODS)
@app.api_route("/api/{path:path}", methods=_METHODS)
async def proxy_api(request: Request, path: str = ""):
    return await _proxy(request)


if ASSETS_DIR.is_dir():
    app.mount("/assets", _AssetFiles(directory=str(ASSETS_DIR)), name="assets")
if KEEPSAKES_DIR.is_dir():
    app.mount("/keepsakes", StaticFiles(directory=str(KEEPSAKES_DIR)), name="keepsakes")
if (WEB_DIR / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
