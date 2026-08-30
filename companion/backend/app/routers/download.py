"""模之屋在线下载接口：创建任务 / 查询进度。"""
import asyncio
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db import engine as db_engine
from ..db import get_session
from ..services import downloader, settings_store
from ..services.importer import import_downloaded

router = APIRouter(prefix="/api/download", tags=["download"])


class DownloadRequest(BaseModel):
    url: str
    category: str = ""  # idle / greet / interact / dance，下载后自动归类提示


def _make_import_cb(category: str = ""):
    def _import_archive_task(archive: Path, info: Dict[str, str], work_name: str):
        from sqlmodel import Session as DbSession
        label = work_name.split("_by_")[0].strip()[:40]
        extra = {"category": category} if category in (
            "idle", "greet", "interact", "dance",
            "close", "orbit", "dolly", "cut", "cinematic",
        ) else None
        with DbSession(db_engine) as s:
            return import_downloaded(
                s, archive, source="aplaybox",
                source_url=f"https://www.aplaybox.com/details/{info['work_type']}/{info['uid']}",
                label=label,
                extra_meta=extra,
            )
    return _import_archive_task


@router.post("")
async def create_download(req: DownloadRequest,
                          session: Session = Depends(get_session)):
    if not downloader.parse_work_url(req.url):
        raise HTTPException(400, "无法识别的模之屋链接")
    try:
        token = (settings_store.get_all(session).get("download") or {}).get("aplaybox_token", "")
        task_id = downloader.create_task(req.url)
        cat = req.category if req.category in (
            "idle", "greet", "interact", "dance",
            "close", "orbit", "dolly", "cut", "cinematic",
        ) else ""
        asyncio.create_task(
            downloader.run_download_task(task_id, req.url, token, _make_import_cb(cat))
        )
        return {"task_id": task_id}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"创建下载失败：{type(exc).__name__}: {exc}") from exc


@router.get("/search")
async def search(keyword: str, kind: str = "motion", page: int = 1):
    client = downloader.AplayboxClient()
    try:
        work_type_id = 1 if kind == "model" else 2
        return await client.search(keyword, work_type_id, page)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"搜索失败: {exc}") from exc
    finally:
        await client.close()


@router.get("/tasks")
def list_tasks():
    return list(downloader.TASKS.values())


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    task = downloader.TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task
