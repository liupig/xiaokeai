"""设置接口。"""
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..services import settings_store
from ..services.llm import test_connection

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.post("/test_llm")
async def test_llm(conf: Dict[str, Any]) -> Dict[str, Any]:
    """用面板里正在编辑（未必已保存）的 LLM 配置做连通性测试。"""
    return await test_connection(conf)


@router.get("")
def get_settings(session: Session = Depends(get_session)) -> Dict[str, Any]:
    return settings_store.get_all(session)


@router.put("")
def update_settings(patch: Dict[str, Any],
                    session: Session = Depends(get_session)) -> Dict[str, Any]:
    return settings_store.update(session, patch)
