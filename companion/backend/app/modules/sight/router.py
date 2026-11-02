"""识别体验的目录和子类配置。小可爱不从这里拿台词。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/api/modules/sight", tags=["modules-sight"])


class SubIn(BaseModel):
    id: str = ""
    label: str = ""
    scene: str = ""
    match: str = ""
    names: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    phases: list[dict[str, Any]] = Field(default_factory=list)
    process_phase: dict[str, str] = Field(default_factory=dict)


@router.get("")
def catalog() -> dict[str, Any]:
    return service.catalog_public()


@router.get("/now")
def now() -> dict[str, Any]:
    from . import session

    return {"lock": session.snapshot(), "brief": service.current().public()}


@router.post("/kinds/{kind_id}/subs")
def add_sub(kind_id: str, body: SubIn) -> dict[str, Any]:
    try:
        return service.add_sub(kind_id, body.model_dump())
    except service.SightError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/kinds/{kind_id}/subs/{sub_id}")
def remove_sub(kind_id: str, sub_id: str) -> dict[str, Any]:
    try:
        service.remove_sub(kind_id, sub_id)
    except service.SightError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}
