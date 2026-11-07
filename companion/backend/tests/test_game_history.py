from sqlmodel import SQLModel, Session, create_engine, select

from app.models import ChatMessage
from app.modules.harness.brief import dance_opening
from app.modules.tarot.router import _record_result, _result_text as tarot_result_text
from app.modules.tavern import router as tavern_router
from app.modules.tavern.router import IdIn, _result_text as tavern_result_text
from app.modules.tavern.rules import Table
from app.routers.chat import _prompt_history


def test_tarot_result_contains_actual_spread_and_question():
    text = tarot_result_text({
        "title": "时间线",
        "question": "接下来会怎样",
        "phase": "linger",
        "cards": [
            {"position": "过去", "name": "愚人", "reversed": False},
            {"position": "现在", "name": "高塔", "reversed": True},
        ],
        "revealed": [0, 1],
        "all_revealed": True,
    })

    assert "时间线" in text
    assert "接下来会怎样" in text
    assert "过去·愚人" in text
    assert "现在·高塔（逆位）" in text
    assert "已完成整局解读" in text


def test_tavern_result_contains_winner_and_places():
    table = Table(her_name="大肥鱼")
    table.phase = "over"
    table.winner = "her"
    table.places = [{"id": "her", "points": 50}, {"id": "you", "points": -30}]

    text = tavern_result_text(table)

    assert "大肥鱼" in text
    assert "+50分" in text
    assert "KE -30分" in text


def test_game_result_enters_prompt_history_not_dance_context():
    result = "【塔罗结果】刚才玩了时间线，已收牌。"
    rows = [ChatMessage(id=1, role="assistant", content=result, kind="game")]

    assert _prompt_history(rows) == [{"role": "assistant", "content": result}]
    assert dance_opening("再来一次", [{"role": "assistant", "content": result}]) == ""
    assert dance_opening("再来一首", [{"role": "assistant", "content": result}]) == ""


def test_tarot_result_is_persisted_as_game_message():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    snap = {
        "title": "时间线",
        "question": "测试",
        "phase": "open",
        "cards": [{"position": "现在", "name": "高塔", "reversed": True}],
        "revealed": [0],
        "all_revealed": False,
    }
    with Session(engine) as session:
        _record_result(7, session, snap)
        row = session.exec(select(ChatMessage)).one()

    assert row.character_id == 7
    assert row.role == "assistant"
    assert row.kind == "game"
    assert "高塔（逆位）" in row.content
    assert "提前收牌" in row.content


def test_tavern_result_is_persisted_as_game_message(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    table = Table(her_name="大肥鱼")
    table.phase = "over"
    table.winner = "her"
    table.places = [{"id": "her", "points": 50}]
    monkeypatch.setattr(tavern_router, "_guard", lambda _session: None)
    monkeypatch.setattr(tavern_router.board, "load", lambda _cid: {})
    tavern_router._TABLES[7] = table

    with Session(engine) as session:
        tavern_router.end_night(IdIn(character_id=7), session)
        row = session.exec(select(ChatMessage)).one()

    assert row.kind == "game"
    assert "大肥鱼" in row.content
    assert "+50分" in row.content
