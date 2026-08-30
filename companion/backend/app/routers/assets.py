"""资产接口：列表 / 导入 / 重扫 / 删除。"""
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from ..db import get_session
from ..models import Asset
from ..paths import ASSETS_DIR, TMP_DIR
from ..services import catalog
from ..services.importer import import_downloaded

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("")
def list_assets(kind: Optional[str] = None,
                session: Session = Depends(get_session)) -> List[Asset]:
    stmt = select(Asset)
    if kind:
        stmt = stmt.where(Asset.kind == kind)
    return session.exec(stmt.order_by(Asset.id)).all()


@router.post("/rescan")
def rescan(session: Session = Depends(get_session)):
    created = catalog.scan_all(session)
    return {"created": len(created)}


@router.post("/import")
async def import_file(file: UploadFile, session: Session = Depends(get_session)):
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in (".zip", ".rar", ".7z", ".vmd", ".vpd", ".vrm", ".glb"):
        raise HTTPException(400, f"不支持的文件类型: {suffix}")
    tmp = TMP_DIR / f"upload_{uuid.uuid4().hex[:8]}{suffix}"
    with open(tmp, "wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        stem = Path(file.filename or "").stem
        created = import_downloaded(session, tmp, label=stem)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"导入失败: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)
    if not created:
        raise HTTPException(422, "压缩包中未识别到可导入的模型、动作或镜头")
    return created


@router.post("/recategorize")
def recategorize(session: Session = Depends(get_session)):
    """按文件名/标签重新归纳全部动作类别。"""
    updated = catalog.recategorize_all(session)
    return {"updated": updated}


@router.patch("/{asset_id}")
def update_asset(asset_id: int, patch: dict,
                 session: Session = Depends(get_session)) -> Asset:
    asset = session.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "资产不存在")
    if "label" in patch:
        asset.label = str(patch["label"])
    if asset.kind == "motion" and patch.get("category"):
        catalog.apply_category(asset, str(patch["category"]))
    if asset.kind == "camera" and patch.get("category"):
        catalog.apply_camera_category(asset, str(patch["category"]))
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, remove_files: bool = False,
                 session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "资产不存在")
    if remove_files:
        target = ASSETS_DIR / asset.path
        if asset.kind == "model" and asset.fmt == "pmx":
            shutil.rmtree(target.parent, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
    session.delete(asset)
    session.commit()
    return {"ok": True}
