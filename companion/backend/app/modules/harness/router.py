"""dsh 模块：状态和关闭。对话本身仍走 /api/chat。"""
from fastapi import APIRouter

from .service import release as release_runtime
from .service import status as runtime_status

router = APIRouter(prefix="/api/modules/harness", tags=["modules-harness"])


@router.get("/status")
def status():
    return runtime_status()


@router.post("/release")
def release():
    release_runtime()
    return runtime_status()
