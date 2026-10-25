"""陪我看的开关。截图仍在眼睛进程，这里只告诉前端有没有新的一句。"""
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from . import along

router = APIRouter(prefix="/api/modules/glance", tags=["modules-glance"])


class AckBody(BaseModel):
    seq: int = 0


@router.get("/along")
def along_status() -> Dict[str, Any]:
    return along.snapshot()


@router.post("/along/stop")
def along_stop() -> Dict[str, Any]:
    along.stop()
    return along.snapshot()


@router.post("/along/ack")
def along_ack(body: AckBody) -> Dict[str, Any]:
    along.ack(body.seq)
    return along.snapshot()
