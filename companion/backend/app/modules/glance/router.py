"""陪我看的开关。截图仍在眼睛进程，这里只告诉前端有没有新的一句。"""
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import along, trace

router = APIRouter(prefix="/api/modules/glance", tags=["modules-glance"])
_LAB_PAGE = Path(__file__).with_name("lab.html")


class AckBody(BaseModel):
    seq: int = 0


class KeepBody(BaseModel):
    on: bool = False


class PowerBody(BaseModel):
    on: bool = False
    character_id: int = 0


@router.get("/along")
def along_status() -> Dict[str, Any]:
    return along.snapshot()


@router.post("/along/stop")
def along_stop() -> Dict[str, Any]:
    along.stop()
    from .eyes_host import shutdown

    shutdown()
    return along.snapshot()


def _power() -> Dict[str, Any]:
    from .eyes_host import eyes_status

    snap = along.snapshot()
    return {**eyes_status(), "along": bool(snap.get("on")), "character_id": snap.get("character_id") or 0}


@router.get("/power")
def power_status() -> Dict[str, Any]:
    return _power()


@router.post("/power")
def power_set(body: PowerBody) -> Dict[str, Any]:
    from .eyes_host import enable_glance, ensure, shutdown

    if body.on:
        enable_glance()
        ensure()
        if body.character_id:
            along.start(int(body.character_id))
    else:
        along.stop()
        shutdown()
    return _power()


@router.post("/along/ack")
def along_ack(body: AckBody) -> Dict[str, Any]:
    along.ack(body.seq)
    return along.snapshot()


@router.get("/lab/page", include_in_schema=False)
def lab_page():
    if not _LAB_PAGE.is_file():
        raise HTTPException(status_code=404, detail="lab page missing")
    return FileResponse(_LAB_PAGE, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/lab/keep")
def lab_keep() -> Dict[str, Any]:
    from . import archive
    return archive.status()


@router.post("/lab/keep")
def lab_keep_set(body: KeepBody) -> Dict[str, Any]:
    from . import archive
    archive.set_keeping(body.on)
    return archive.status()


@router.get("/lab")
def lab_feed(limit: int = 40, before: str = "", after: str = "") -> Dict[str, Any]:
    return trace.feed(limit=limit, before=before, after=after)


@router.post("/lab/clear")
def lab_clear() -> Dict[str, Any]:
    trace.clear()
    return {"ok": True}


@router.post("/lab/open")
def lab_open() -> Dict[str, Any]:
    """设置里点一下才打开。服务启动时不再弹出。"""
    import webbrowser

    from .archive import lab_url

    url = lab_url()
    try:
        opened = webbrowser.open(url)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not opened:
        raise HTTPException(status_code=500, detail="browser did not open")
    return {"ok": True, "url": url}


@router.get("/lab/{item_id}/{kind}/{index}")
def lab_shot(item_id: str, kind: str, index: int):
    blob = trace.shot(item_id, kind, index)
    if not blob:
        raise HTTPException(status_code=404, detail="shot missing")
    return Response(blob, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
