"""镜头审查标记：SQLite 表 cam_review 一行一条，JSON 文件做可读备份。"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict
from urllib.parse import unquote

from sqlmodel import Session, select

from ..models import CamReview, Setting
from ..paths import DATA_DIR

KEY = "cam_review"
FILE_PATH: Path = DATA_DIR / "cam_review.json"
TZ_CN = timezone(timedelta(hours=8))
RETIRED_CAM_KEYS = frozenset({"move:low45"})


def _cam_key(combo_id: str) -> str:
    parts = combo_id.split("|")
    if len(parts) < 2:
        return ""
    try:
        return unquote(parts[1])
    except Exception:
        return parts[1]


def _drop_retired(verdicts: Dict[str, str]) -> Dict[str, str]:
    return {k: v for k, v in verdicts.items() if _cam_key(k) not in RETIRED_CAM_KEYS}


def _empty() -> Dict[str, Any]:
    return {"version": 3, "updated_at": "", "verdicts": {}}


def _now() -> datetime:
    return datetime.now(TZ_CN).replace(tzinfo=None)


def _read_file() -> Dict[str, Any] | None:
    if not FILE_PATH.exists():
        return None
    try:
        data = json.loads(FILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_setting_blob(session: Session) -> Dict[str, Any] | None:
    row = session.get(Setting, KEY)
    if not row:
        return None
    try:
        data = json.loads(row.value)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalize(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    data = _empty()
    if not raw:
        return data
    verdicts = raw.get("verdicts")
    if isinstance(verdicts, dict):
        data["verdicts"] = _drop_retired({
            str(k): v for k, v in verdicts.items() if v in ("ok", "bad")
        })
    data["version"] = int(raw.get("version") or 3)
    data["updated_at"] = str(raw.get("updated_at") or "")
    return data


def _rows_to_payload(rows: list[CamReview]) -> Dict[str, Any]:
    verdicts = _drop_retired(
        {r.combo_id: r.verdict for r in rows if r.verdict in ("ok", "bad")}
    )
    latest = max((r.updated_at for r in rows), default=None)
    updated = ""
    if latest:
        updated = latest.isoformat(timespec="seconds")
        if not updated.endswith("+08:00") and "T" in updated:
            updated = f"{updated}+08:00"
    return {"version": 3, "updated_at": updated, "verdicts": verdicts}


def _write_json(payload: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(FILE_PATH)


def load(session: Session) -> Dict[str, Any]:
    migrate_if_needed(session)
    rows = list(session.exec(select(CamReview)).all())
    retired = [r for r in rows if _cam_key(r.combo_id) in RETIRED_CAM_KEYS]
    if retired:
        for r in retired:
            session.delete(r)
        session.commit()
        rows = [r for r in rows if r not in retired]
        payload = _rows_to_payload(rows)
        payload["updated_at"] = datetime.now(TZ_CN).isoformat(timespec="seconds")
        _write_json({
            "version": 3,
            "updated_at": payload["updated_at"],
            "verdicts": payload["verdicts"],
        })
    data = _rows_to_payload(rows) if rows else _empty()
    data["path"] = str(FILE_PATH)
    data["table"] = "cam_review"
    return data


def save(session: Session, verdicts: Dict[str, str]) -> Dict[str, Any]:
    clean = _drop_retired({str(k): v for k, v in verdicts.items() if v in ("ok", "bad")})
    now = _now()
    existing = {r.combo_id: r for r in session.exec(select(CamReview)).all()}
    keep = set(clean)
    for cid, verdict in clean.items():
        row = existing.get(cid)
        if row is None:
            session.add(CamReview(combo_id=cid, verdict=verdict, updated_at=now))
        elif row.verdict != verdict:
            row.verdict = verdict
            row.updated_at = now
            session.add(row)
    for cid, row in existing.items():
        if cid not in keep:
            session.delete(row)
    blob = session.get(Setting, KEY)
    if blob:
        session.delete(blob)
    session.commit()
    payload = {
        "version": 3,
        "updated_at": datetime.now(TZ_CN).isoformat(timespec="seconds"),
        "verdicts": clean,
    }
    _write_json(payload)
    payload["path"] = str(FILE_PATH)
    payload["table"] = "cam_review"
    return payload


def migrate_if_needed(session: Session) -> int:
    """表是空的时候，从 JSON / 旧 setting 大字段迁进 cam_review。"""
    if session.exec(select(CamReview)).first():
        return 0
    file_data = _normalize(_read_file())
    blob_data = _normalize(_read_setting_blob(session))
    verdicts = dict(blob_data["verdicts"])
    verdicts.update(file_data["verdicts"])
    if not verdicts:
        return 0
    now = _now()
    for cid, verdict in verdicts.items():
        session.add(CamReview(combo_id=cid, verdict=verdict, updated_at=now))
    blob = session.get(Setting, KEY)
    if blob:
        session.delete(blob)
    session.commit()
    _write_json({
        "version": 3,
        "updated_at": datetime.now(TZ_CN).isoformat(timespec="seconds"),
        "verdicts": verdicts,
    })
    return len(verdicts)
