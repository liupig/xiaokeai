"""角色卡 CRUD + 酒馆卡导入/导出。"""
import re
from pathlib import Path
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlmodel import Session, select

from ..db import get_session
from ..models import (
    Asset, Character, ChatMessage, MemoryEpisode, MemoryExtractCursor, MemoryFact,
    PinnedMessage,
)
from ..modules.character import exporter as card_exporter
from ..modules.character import importer as card_importer
from ..modules.character.card import parse_greetings
from ..paths import AVATARS_DIR

router = APIRouter(prefix="/api/characters", tags=["characters"])

# PUT / 更新时允许写回的列（其余列保持原值）
_EDITABLE_FIELDS = (
    "name", "model_asset_id", "persona", "boundary", "greeting",
    "voice", "emotion_map", "idle_motion",
    "personality", "scenario", "mes_example", "greetings", "lorebook",
    "tags", "creator", "card_version",
)


@router.get("")
def list_characters(session: Session = Depends(get_session)) -> List[Character]:
    return session.exec(select(Character).order_by(Character.id)).all()


@router.post("")
def create_character(char: Character, session: Session = Depends(get_session)) -> Character:
    char.id = None
    session.add(char)
    session.commit()
    session.refresh(char)
    return char


@router.put("/{char_id}")
def update_character(char_id: int, patch: Character,
                     session: Session = Depends(get_session)) -> Character:
    char = session.get(Character, char_id)
    if not char:
        raise HTTPException(404, "角色不存在")
    for field in _EDITABLE_FIELDS:
        setattr(char, field, getattr(patch, field))
    session.add(char)
    session.commit()
    session.refresh(char)
    return char


@router.post("/import")
async def import_character(file: UploadFile, session: Session = Depends(get_session)) -> Character:
    """拖入酒馆 PNG 卡或 JSON 卡，解析入库；PNG 原图留档做角色封面。"""
    data = await file.read()
    try:
        parsed = card_importer.parse_card(data, filename=file.filename or "")
    except card_importer.CardParseError as exc:
        raise HTTPException(400, str(exc)) from exc
    fields = card_importer.card_to_character_fields(parsed)
    is_png = data[:8] == card_importer.PNG_MAGIC
    fields["avatar_path"] = "__pending__" if is_png else ""
    char = Character(**fields)
    session.add(char)
    session.commit()
    session.refresh(char)
    if is_png:
        avatar_name = f"char_{char.id}.png"
        (AVATARS_DIR / avatar_name).write_bytes(data)
        char.avatar_path = avatar_name
        session.add(char)
        session.commit()
        session.refresh(char)
    return char


@router.get("/{char_id}/export")
def export_character(char_id: int, session: Session = Depends(get_session)) -> Response:
    """导出 SillyTavern v2 PNG 角色卡，可直接拖回酒馆。"""
    char = session.get(Character, char_id)
    if not char:
        raise HTTPException(404, "角色不存在")
    try:
        png = card_exporter.export_png_bytes(char)
    except Exception as exc:
        raise HTTPException(500, f"导出失败：{exc}") from exc
    filename = card_exporter.export_filename(char)
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", char.name or "character") or "character"
    utf8_name = quote(filename)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}.png\"; filename*=UTF-8''{utf8_name}"
            )
        },
    )


@router.post("/{char_id}/greeting")
def character_greeting(char_id: int, session: Session = Depends(get_session)) -> dict:
    """开场白：角色卡里写的第一句，直接由她说出来（不调模型）。

    对齐酒馆的 first_mes：开场白是聊天记录的一部分，落库为 assistant welcome。
    幂等：上一条已经是同一段开场白就不重复插。
    """
    char = session.get(Character, char_id)
    if not char:
        raise HTTPException(404, "角色不存在")
    text = (char.greeting or "").strip()
    if not text:
        variants = parse_greetings(getattr(char, "greetings", "") or "")
        text = variants[0].strip() if variants else ""
    if not text:
        return {"spoken": False, "text": "", "message_id": None}
    latest = session.exec(
        select(ChatMessage)
        .where(ChatMessage.character_id == char_id)
        .order_by(ChatMessage.id.desc()).limit(1)
    ).first()
    if latest and latest.role == "assistant" and (latest.content or "").strip() == text:
        return {"spoken": False, "text": text, "message_id": latest.id}
    row = ChatMessage(
        character_id=char_id, role="assistant", content=text,
        full_content=text, kind="welcome",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"spoken": True, "text": text, "message_id": row.id}


@router.get("/{char_id}/avatar")
def character_avatar(char_id: int, session: Session = Depends(get_session)) -> FileResponse:
    char = session.get(Character, char_id)
    if not char or not (char.avatar_path or "").strip():
        raise HTTPException(404, "没有封面")
    fp = (AVATARS_DIR / Path(char.avatar_path).name).resolve()
    try:
        fp.relative_to(AVATARS_DIR.resolve())
    except ValueError:
        raise HTTPException(404, "没有封面")
    if not fp.is_file():
        raise HTTPException(404, "没有封面")
    return FileResponse(fp)


@router.delete("/{char_id}")
def delete_character(char_id: int, session: Session = Depends(get_session)):
    char = session.get(Character, char_id)
    if not char:
        raise HTTPException(404, "角色不存在")
    for model in (ChatMessage, MemoryFact, MemoryEpisode, PinnedMessage):
        rows = session.exec(select(model).where(model.character_id == char_id)).all()
        for row in rows:
            session.delete(row)
    cursor = session.get(MemoryExtractCursor, char_id)
    if cursor is not None:
        session.delete(cursor)
    session.delete(char)
    session.commit()
    avatar = AVATARS_DIR / f"char_{char_id}.png"
    if avatar.is_file():
        try:
            avatar.unlink()
        except OSError:
            pass
    return {"ok": True}
