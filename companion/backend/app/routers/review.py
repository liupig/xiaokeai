"""镜头审查标记接口。"""
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..services import head_review_store, review_store

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/cam")
def get_cam_review(session: Session = Depends(get_session)) -> Dict[str, Any]:
    data = review_store.load(session)
    data["path"] = str(review_store.FILE_PATH)
    return data


@router.put("/cam")
def put_cam_review(body: Dict[str, Any],
                   session: Session = Depends(get_session)) -> Dict[str, Any]:
    verdicts = body.get("verdicts") if isinstance(body.get("verdicts"), dict) else body
    if not isinstance(verdicts, dict):
        verdicts = {}
    return review_store.save(session, {str(k): str(v) for k, v in verdicts.items()})


@router.put("/head-auto")
def put_head_auto_review(body: Dict[str, Any]) -> Dict[str, Any]:
    return head_review_store.save_motion(body)
