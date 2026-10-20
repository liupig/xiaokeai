"""HTTP door for the local coin box.

The compiled box decides every mint, including a wish. This module does not
choose the coin amount. After a wish it may add one spoken line and one memory
fact.

The line comes from the chat model in the reply language. It must contain the
integer coin count the box already chose. An empty line, a line longer than 80
characters, or a line that drops that number is discarded. The client then
speaks the local result sentence.

Memory, when that module is on and a character is current, updates a single
fact whose text starts with "[wish]". A new wish rewrites that row with the
lifetime count, today's props, and today's coins. It does not insert a row
per wish. The write runs on a daemon thread so a slow memory worker cannot
hold the response, and a failure there does not undo the mint.
"""
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..modules.flags import enabled
from ..modules.memory import worker as memory_worker
from ..services import coins_box as coins
from ..services import llm as llm_service
from ..services import settings_store
from ..services.coins_box import CoinError

router = APIRouter(prefix="/api/coins", tags=["coins"])

_NAMES: Dict[str, Dict[str, str]] = {
    "zh-CN": {
        "work": "工作", "phone": "手机", "computer": "电脑", "bracelet": "手串",
        "key": "钥匙", "letter": "信", "worry": "烦恼", "magnet": "磁铁",
        "card": "信用卡", "alarm": "闹钟", "sock": "一只袜子", "meeting": "周一例会",
    },
    "en": {
        "work": "work", "phone": "a phone", "computer": "a laptop", "bracelet": "a bracelet",
        "key": "a key", "letter": "a letter", "worry": "a worry", "magnet": "a magnet",
        "card": "a credit card", "alarm": "an alarm clock", "sock": "one sock", "meeting": "a Monday meeting",
    },
    "ja": {
        "work": "仕事", "phone": "スマホ", "computer": "パソコン", "bracelet": "腕輪",
        "key": "鍵", "letter": "手紙", "worry": "悩み", "magnet": "磁石",
        "card": "クレジットカード", "alarm": "目覚まし時計", "sock": "靴下片っぽ", "meeting": "月曜の会議",
    },
    "ko": {
        "work": "일", "phone": "휴대폰", "computer": "노트북", "bracelet": "팔찌",
        "key": "열쇠", "letter": "편지", "worry": "걱정", "magnet": "자석",
        "card": "신용카드", "alarm": "자명종", "sock": "양말 한 짝", "meeting": "월요일 회의",
    },
}

_MEMORY = {
    "zh-CN": "[wish] 许愿池玩了{times}次。最近扔进了{items}，落下{n}枚金币。",
    "en": "[wish] Wished {times} times. Last throw: {items}. {n} coins came back.",
    "ja": "[wish] 願いの池を{times}回やった。この前は{items}を投げて、コイン{n}枚が落ちた。",
    "ko": "[wish] 소원 연못을 {times}번 했다. 이번에는 {items}를 던졌고, 코인 {n}개가 떨어졌다.",
}


class PayBody(BaseModel):
    to: str = ""
    amount_milli: int = 0


class RedeemBody(BaseModel):
    note: str = ""


class WishBody(BaseModel):
    character_id: int = 0


def _guard(fn):
    try:
        return fn()
    except CoinError as exc:
        raise HTTPException(status_code=400, detail=exc.code)


def _lang(session: Session) -> str:
    try:
        conf = settings_store.get_all(session)
        code = str((conf.get("locale") or {}).get("reply") or "zh-CN")
    except Exception:
        code = "zh-CN"
    low = code.replace("_", "-").lower()
    if low.startswith("en"):
        return "en"
    if low.startswith("ja"):
        return "ja"
    if low.startswith("ko"):
        return "ko"
    return "zh-CN"


def _item_names(lang: str, throws: List[Dict[str, Any]]) -> str:
    table = _NAMES.get(lang) or _NAMES["zh-CN"]
    names = [table.get(str(item.get("id") or ""), str(item.get("id") or "")) for item in throws]
    sep = ", " if lang == "en" else "、"
    return sep.join(names)


def _remember(character_id: int, lang: str, row: Dict[str, Any]) -> None:
    if character_id <= 0:
        return
    try:
        times = int(row.get("wish_times") or 0)
        coins_n = max(1, int(row.get("drop_milli") or 0) // 1000)
        items = _item_names(lang, list(row.get("throws") or []))
        text = _MEMORY.get(lang, _MEMORY["zh-CN"]).format(times=times, items=items, n=coins_n)
        fact_id = None
        for fact in memory_worker.list_facts(character_id):
            fid = str(fact.get("id") or "")
            if fid.isdigit() and str(fact.get("content") or "").startswith("[wish]"):
                fact_id = fid
                break
        memory_worker.upsert_fact(
            character_id,
            fact_id=fact_id,
            kind="event",
            content=text,
            importance=0.62,
        )
    except Exception as exc:
        print(f"[wish] memory skipped: {exc}")


async def _wish_line(session: Session, lang: str, row: Dict[str, Any]) -> str:
    try:
        conf = settings_store.get_all(session)
        llm_conf = dict(conf.get("llm") or {})
    except Exception:
        return ""
    coins_n = max(1, int(row.get("drop_milli") or 0) // 1000)
    items = _item_names(lang, list(row.get("throws") or []))
    lang_name = {"zh-CN": "简体中文", "en": "English", "ja": "日本語", "ko": "한국어"}.get(lang, "简体中文")
    messages = [
        {
            "role": "system",
            "content": (
                "你在给许愿池写一句旁白。只返回 JSON："
                '{"line":"一句话"}。必须使用指定语言。'
                "金币数量必须原样使用，不许改数字，不许再许诺更多金币。"
            ),
        },
        {
            "role": "user",
            "content": f"语言：{lang_name}。扔进池子的是：{items}。落下金币：{coins_n}。",
        },
    ]
    try:
        parsed = await llm_service.complete_json(llm_conf, messages, max_tokens=120, timeout=6)
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""
    line = str(parsed.get("line") or "").strip()
    if not line or len(line) > 80:
        return ""
    if str(coins_n) not in line:
        return ""
    return line


@router.post("/heartbeat")
def heartbeat() -> Dict[str, Any]:
    return _guard(coins.heartbeat)


@router.get("/preview")
def preview(sec: int = 0) -> Dict[str, Any]:
    return _guard(lambda: coins.preview(sec))


@router.post("/pay")
def pay(body: PayBody) -> Dict[str, Any]:
    return _guard(lambda: coins.pay(body.to, body.amount_milli))


@router.post("/redeem")
def redeem(body: RedeemBody) -> Dict[str, Any]:
    return _guard(lambda: coins.redeem(body.note))


@router.post("/wish")
async def wish(body: Optional[WishBody] = None, session: Session = Depends(get_session)) -> Dict[str, Any]:
    row = _guard(coins.wish)
    lang = _lang(session)
    row["line"] = await _wish_line(session, lang, row)
    character_id = int((body.character_id if body else 0) or 0)
    if enabled(session, "memory") and character_id > 0:
        threading.Thread(
            target=_remember,
            args=(character_id, lang, dict(row)),
            daemon=True,
        ).start()
    return row


@router.get("/balance")
def balance() -> Dict[str, int]:
    return _guard(lambda: {"balance_milli": coins.balance()})
