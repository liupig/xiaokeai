"""剧照 / 短片存档。"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ...db import get_session
from ...models import Keepsake
from ...paths import KEEPSAKES_DIR
from ..flags import enabled

router = APIRouter(prefix="/api/modules/keepsakes", tags=["modules-keepsake"])

STILL_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
CLIP_EXTS = {".webm", ".mp4", ".mkv"}
SAFE_NAME = re.compile(
    r"^[0-9]+_[a-fA-F0-9]+\.(jpg|jpeg|png|webp|mp4|webm|mkv)$", re.I)
MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".mp4": "video/mp4", ".webm": "video/webm",
    ".mkv": "video/x-matroska",
}


def _file_url(name: str) -> str:
    return f"/api/modules/keepsakes/file/{name}"


def _to_dict(row: Keepsake) -> Dict[str, Any]:
    name = Path(row.path).name if row.path else ""
    return {
        "id": row.id,
        "character_id": row.character_id,
        "kind": row.kind,
        "url": _file_url(name) if name else "",
        "mime": row.mime,
        "caption": row.caption,
        "quote": row.quote,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


@router.get("/file/{filename}")
def get_file(filename: str) -> FileResponse:
    """走 /api 代理，避免前端把 /keepsakes 当成 SPA 页面。"""
    name = Path(filename).name
    if not SAFE_NAME.match(name):
        raise HTTPException(404, "not found")
    fp = KEEPSAKES_DIR / name
    if not fp.is_file():
        raise HTTPException(404, "not found")
    media = MIME_BY_EXT.get(fp.suffix.lower()) or "application/octet-stream"
    return FileResponse(fp, media_type=media, filename=name, content_disposition_type="inline")


@router.get("/{character_id}")
def list_keepsakes(character_id: int, session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    if not enabled(session, "keepsake"):
        return []
    rows = session.exec(
        select(Keepsake)
        .where(Keepsake.character_id == character_id)
        .order_by(Keepsake.id.desc())
    ).all()
    return [_to_dict(r) for r in rows]


@router.post("")
async def upload_keepsake(
    character_id: int = Form(...),
    kind: str = Form("still"),
    caption: str = Form(""),
    quote: str = Form(""),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    if not enabled(session, "keepsake"):
        raise HTTPException(404, "keepsake module off")
    kind = "clip" if kind == "clip" else "still"
    name = file.filename or "capture.bin"
    ext = Path(name).suffix.lower() or (".webm" if kind == "clip" else ".jpg")
    if kind == "still" and ext not in STILL_EXTS:
        ext = ".jpg"
    if kind == "clip" and ext not in CLIP_EXTS:
        ext = ".webm"
    fname = f"{character_id}_{uuid.uuid4().hex}{ext}"
    dest = KEEPSAKES_DIR / fname
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    dest.write_bytes(data)
    mime = file.content_type or ("video/webm" if kind == "clip" else "image/jpeg")
    row = Keepsake(
        character_id=character_id,
        kind=kind,
        path=fname,
        mime=mime,
        caption=(caption or "")[:80],
        quote=(quote or "")[:120],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_dict(row)


@router.delete("/{keepsake_id}")
def delete_keepsake(keepsake_id: int, session: Session = Depends(get_session)) -> Dict[str, bool]:
    if not enabled(session, "keepsake"):
        raise HTTPException(404, "keepsake module off")
    row = session.get(Keepsake, keepsake_id)
    if not row:
        raise HTTPException(404, "not found")
    fp = KEEPSAKES_DIR / Path(row.path).name
    if fp.exists():
        try:
            fp.unlink()
        except OSError:
            pass
    session.delete(row)
    session.commit()
    return {"ok": True}
