"""魅影酒馆：入座、出牌、揭穿。牌局只留在这次进程里。"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from ...db import get_session
from ...models import Character
from ...services import settings_store
from ..flags import enabled
from ...services import coins, ledger
from . import board, habits, judge
from .rules import RuleError, Table

router = APIRouter(prefix="/api/modules/tavern", tags=["modules-tavern"])

_LOCK = threading.Lock()
_TABLES: Dict[int, Table] = {}


def _guard(session: Session) -> None:
    if not enabled(session, "tavern"):
        raise HTTPException(404, "off")


class StartIn(BaseModel):
    character_id: int = 0
    her_name: str = "她"
    deck: str = "rose"


class PlayIn(BaseModel):
    character_id: int = 0
    cards: List[str] = Field(default_factory=list)


class NameIn(BaseModel):
    character_id: int = 0
    face: str = ""


class IdIn(BaseModel):
    character_id: int = 0


def _table(cid: int) -> Table:
    table = _TABLES.get(cid)
    if table is None:
        raise HTTPException(404, "idle")
    return table


def _coins(points: int) -> int:
    """名次换成金币。正数按对话入账，负数烧掉。余额不够就扣到零。"""
    points = int(points)
    if points > 0:
        try:
            ledger.call("grant_talk", ["", "", points * 4000])
        except Exception as exc:
            print(f"[tavern] grant skipped: {exc}")
            return 0
        return points
    if points < 0:
        try:
            have = int(coins.balance())
            take = min(-points * 1000, max(0, have))
            if take <= 0:
                return 0
            coins.pay(coins.BURN, take)
        except Exception as exc:
            print(f"[tavern] pay skipped: {exc}")
            return 0
        return -(take // 1000)
    return 0


def _present(table: Table, cid: int) -> dict:
    habits.observe(cid, table.night, table.note)
    if table.phase == "over" and not table.paid:
        board.apply(cid, table.places)
        you = next((row for row in table.places if row.get("id") == "you"), None)
        table.coin_delta = _coins(int(you["points"]) if you else 0)
        table.paid = True
    view = table.view()
    view["board"] = board.load(cid)
    if table.phase == "over":
        view["coin_delta"] = table.coin_delta
        try:
            view["balance_milli"] = int(coins.balance())
        except Exception:
            pass
    return view


def _run(cid: int, fn) -> dict:
    with _LOCK:
        table = _table(cid)
        try:
            fn(table)
        except RuleError as exc:
            raise HTTPException(400, str(exc)) from exc
        return _present(table, cid)


@router.get("/state")
def state(character_id: int = 0, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    with _LOCK:
        table = _TABLES.get(character_id)
        if table is None:
            return {"phase": "idle", "board": board.load(character_id)}
        return _present(table, character_id)


@router.post("/start")
def start(body: StartIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    name = (body.her_name or "她").strip()[:24] or "她"
    with _LOCK:
        table = Table(her_name=name, deck=(body.deck or "rose").strip())
        table.start()
        _TABLES[body.character_id] = table
        return _present(table, body.character_id)


@router.post("/name")
def name_suit(body: NameIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)

    def act(table: Table) -> None:
        if table.phase != "name" or table.seats[table.turn].id != "you":
            raise RuleError("turn")
        table.name(body.face)

    return _run(body.character_id, act)


@router.post("/play")
def play(body: PlayIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)

    def act(table: Table) -> None:
        if table.phase != "act" or table.seats[table.turn].id != "you":
            raise RuleError("turn")
        table.play(body.cards)

    return _run(body.character_id, act)


@router.post("/call")
def call(body: IdIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)

    def act(table: Table) -> None:
        if table.phase != "act" or table.seats[table.turn].id != "you":
            raise RuleError("turn")
        table.call()

    return _run(body.character_id, act)


@router.post("/ack")
def ack(body: IdIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return _run(body.character_id, lambda table: table.ack())


@router.post("/next")
def next_round(body: IdIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    return _run(body.character_id, lambda table: table.open_next())


@router.post("/end")
def end_night(body: IdIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """结束这一局，回到选人和选牌。不记这一局的胜负。"""
    _guard(session)
    with _LOCK:
        _TABLES.pop(body.character_id, None)
        return {"phase": "idle", "board": board.load(body.character_id)}


def _voice(session: Session, character_id: int, who: str, her_name: str) -> str:
    if who == "qin":
        return "你是 XiaO，坐在左手边。台词短。打牌不按固定性格，只按这一局的目标和局面分析。"
    if who == "bar":
        return "你是 AI，坐在右手边。台词利落。打牌不按固定性格，只按这一局的目标和局面分析。"
    persona = ""
    row = session.get(Character, character_id) if character_id else None
    if row is not None and (row.persona or "").strip():
        persona = " ".join(row.persona.split())[:180]
    name = her_name or (row.name if row is not None else "") or "她"
    text = f"你是{name}，坐在对面。台词可以带你的性格。打牌不按固定性格，只按这一局的目标和局面分析。"
    if persona:
        text += "说话的性格：" + persona
    return text


@router.post("/step")
def step(body: IdIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    _guard(session)
    with _LOCK:
        table = _table(body.character_id)
        if table.phase not in ("act", "name"):
            raise HTTPException(400, "wait")
        seat = table.seats[table.turn]
        if seat.kind == "human":
            raise HTTPException(400, "turn")
        table.memory = habits.bias(body.character_id)
        her_name = table.her_name
        brief = table.brief()
        brief["dossier"] = habits.lines(body.character_id, her_name)
        token = (id(table), table.seq)
        who = seat.id
    decision = judge.decide(
        settings_store.get_all(session).get("llm") or {},
        brief,
        _voice(session, body.character_id, who, her_name),
    )
    with _LOCK:
        table = _table(body.character_id)
        if (id(table), table.seq) != token:
            return _present(table, body.character_id)
        try:
            table.step(decision)
        except RuleError as exc:
            raise HTTPException(400, str(exc)) from exc
        return _present(table, body.character_id)
