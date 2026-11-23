import asyncio
import json
import os
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.models import Character, CharacterLife
from app.modules.character_life import events, service


def test_curated_events_use_traits_without_gender_stereotypes_and_avoid_recent():
    card = "性别：女。二十二岁，宠物美容师，爱跑步。"
    traits = events.profile(card, {})
    assert traits == {"stage": "adult", "gender": "女", "world": "everyday", "tags": ["running", "pet_care"]}
    start = datetime(2026, 11, 19).date()
    recent = []
    for offset in range(6):
        day = start + timedelta(days=offset)
        event = events.select_event(1, day, traits, recent)
        assert event == events.select_event(1, day, {**traits, "gender": "男"}, recent)
        assert event.key not in recent
        recent.append(event.key)
    assert set(recent) & {"apron-back", "last-appointment"}
    assert any(key in recent for key in ("night-route", "slow-partner"))
    assert "pet_care" not in events.profile(card, {"occupation": "花店学徒"})["tags"]
    assert events.profile("十五岁，在古代王国学琴", {})["stage"] == "minor"
    assert events.ending("unmarked-door", 1, start) in next(item.endings for item in events.EVENTS if item.key == "unmarked-door")
    assert "跑" in events.private_story(1, traits, card)[1]
    assert events.private_story(1, traits, card + "小秘密：藏着一张旧船票。") is None
    assert events.contacts("跑友阿榆约好这周训练，室友：小秦。") == {"running": "阿榆", "shared_home": "小秦"}


@pytest.mark.parametrize(("card", "occupation", "expected_tag"), [
    ("二十二岁，宠物美容师，喜欢跑步。", "宠物美容师", "pet_care"),
    ("30岁，护士，最近常上夜班。", "护士", "care_work"),
    ("性别：男，44岁，夜班保安。", "夜班保安", "night_shift"),
    ("性别：非二元，软件工程师，独居，爱木工。", "软件工程师", "software"),
    ("十五岁，高中生，爱看小说。", "高中生", "student"),
    ("68岁，退休，喜欢种花。", "退休", "retired"),
    ("36岁，和家人同住，照护老人。", "", "caregiving"),
    ("插画师，自由职业，刚搬到这里。", "自由职业插画师", "creative_work"),
    ("古代王国的学徒，十五岁。", "", "fantasy"),
])
def test_catalog_covers_distinct_profiles_over_sixty_days(card, occupation, expected_tag):
    traits = events.profile(card, {"occupation": occupation})
    assert expected_tag in traits["tags"]
    start = datetime(2026, 11, 19).date()
    trail = []
    selected = []
    for offset in range(60):
        event = events.select_event(23, start + timedelta(days=offset), traits, trail)
        assert event.key not in trail[-8:]
        assert not event.tag or event.tag in traits["tags"]
        assert not event.world or event.world == traits["world"]
        if traits["stage"] != "adult":
            assert not event.adult
        selected.append(event)
        trail = [*trail, event.key][-16:]
    assert len({event.lane for event in selected}) >= 4
    assert any(event.tag == expected_tag for event in selected)
    assert len({event.key for event in selected}) >= 15


def test_journal_thread_waits_for_a_follow_up_and_then_closes():
    start = datetime(2026, 11, 19).date()
    early = start + timedelta(days=1)
    due = start + timedelta(days=2)
    first = service._advance({
        "journal_plan": "票根上的地址，周六去看看",
        "journal_trace": "票背写着：西门过了六点开",
        "journal_month": "没有前文的假结局",
    }, {}, None, start)
    assert first["journal_month"] == ""
    assert first["journal_thread"]["follow_up_on"] == due.isoformat()
    waiting = service._advance({
        "journal_plan": "不相关的新计划", "journal_month": "过早剧透",
    }, first, start, early)
    assert waiting["journal_plan"] == first["journal_plan"]
    assert waiting["journal_month"] == ""
    closed = service._advance({
        "journal_plan": first["journal_plan"], "journal_month": "西门开了，里面是一家旧唱片铺",
    }, waiting, early, due)
    assert closed["journal_month"] == "西门开了，里面是一家旧唱片铺"
    assert closed["journal_plan"] == "" and "journal_thread" not in closed


def test_catalog_controls_an_arc_even_when_model_suggests_a_different_ending(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'arc.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(service, "engine", engine)
    with Session(engine) as session:
        session.add(Character(id=4, name="清宵", character_life_enabled=True))
        session.commit()
    opening = next(item for item in events.EVENTS if item.key == "unmarked-door")
    monkeypatch.setattr(events, "select_event", lambda *_: opening)

    async def render(*_, **_options):
        return {"today": "模型临时编的事", "journal_today": "手记正文", "journal_month": "模型临时编的结局"}

    monkeypatch.setattr(service, "complete_json", render)

    async def run():
        start = datetime(2026, 11, 19)
        for offset in range(4):
            await service.context(4, "清宵", "性别：女，爱跑步", {},
                                  refresh=True, now=start + timedelta(days=offset))
            with Session(engine) as session:
                row = session.get(CharacterLife, 4)
                journal = service.public_journal(row, [])
                state = json.loads(row.state)
            if offset < 2:
                assert state["today"] == opening.fact
                assert journal["journal_plan"] == opening.plan
                assert journal["follow_up_on"] == "2026-11-21"
                assert not journal.get("journal_month")
            elif offset == 2:
                assert journal["journal_month"] in opening.endings
                assert state["today"] == journal["journal_month"]
                assert not journal.get("journal_plan")
                assert "journal_thread" not in state
            else:
                assert journal["milestones"][0]["text"] in opening.endings
                assert journal["milestones"][0]["date"] == "2026-11-21"
                assert [entry["date"] for entry in journal["entries"]] == ["2026-11-19", "2026-11-20", "2026-11-21"]

    asyncio.run(run())


def test_life_timeline_reuses_daily_record_and_preserves_continuity(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'life.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(service, "engine", engine)
    with Session(engine) as session:
        session.add(Character(id=1, name="清宵", character_life_enabled=True))
        session.add(Character(id=2, name="另一位角色", character_life_enabled=True))
        session.commit()

    calls = []

    async def generate(_conf, messages, **_options):
        data = json.loads(messages[-1]["content"])
        calls.append(data)
        if data["date"] == "2027-11-04":
            return None
        changed = bool(data["previous"])
        return {
            "age": 40 if changed else 22,
            "occupation": "花店学徒" if changed else "宠物美容师",
            "month": "第一天去花店上工" if changed else "跟阿榆学插花",
            "week": "准备插花展" if changed else "和阿榆去花市",
            "today": f"{data['name']}去了花市",
            "morning": "去花市", "mood": "有点紧张",
            "secret_hint": "留着一片干花", "secret": "干花来自她第一次演出",
        }

    monkeypatch.setattr(service, "complete_json", generate)

    async def fetch(day, character_id=1, refresh=True):
        name = "清宵" if character_id == 1 else "另一位角色"
        message = await service.context(
            character_id, name, "角色档案，小秘密：留着一片干花。", {}, refresh=refresh, now=datetime.fromisoformat(day),
        )
        return json.loads(message.splitlines()[-1]) if message else {}

    async def run():
        assert await fetch("2026-11-02", refresh=False) == {}
        first, repeated = await asyncio.gather(fetch("2026-11-02"), fetch("2026-11-02"))
        assert first == repeated and len(calls) == 1
        assert first["age"] == 22 and first["occupation"] == "宠物美容师"
        assert "private_story" not in first

        next_day = await fetch("2026-11-03")
        assert next_day["occupation"] == first["occupation"]
        assert next_day["week"] == first["week"]
        next_week = await fetch("2026-11-09")
        assert next_week["week"] == "准备插花展"
        assert next_week["month"] == first["month"]
        assert (await fetch("2026-11-20"))["private_story"] == "干花来自她第一次演出"

        later = await fetch("2027-11-03")
        assert later["age"] == 23
        assert later["occupation"] == "花店学徒"
        assert later["past"][0]["month"] == first["month"]
        fallback = await fetch("2027-11-04")
        assert fallback["as_of"] == "2027-11-04"
        assert fallback["today"] == calls[-1]["selected_event"]["fact"]
        other = await fetch("2027-11-04", character_id=2, refresh=False)
        assert not other
        assert (await fetch("2027-11-03", character_id=2))["today"] == calls[-1]["selected_event"]["fact"]
        assert calls[-1]["name"] == "另一位角色"

    asyncio.run(run())
    with Session(engine) as session:
        assert session.get(CharacterLife, 1).as_of == "2027-11-04"


@pytest.mark.parametrize("live_model", [
    False,
    pytest.param(True, marks=pytest.mark.skipif(
        os.getenv("TEST_CHARACTER_LIFE_LIVE") != "1", reason="requires configured chat model")),
])
def test_character_life_through_settings_and_chat(tmp_path, monkeypatch, live_model):
    from app import db
    from app.routers import characters, chat, settings
    from app.services import llm, settings_store

    engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}",
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(service, "engine", engine)
    monkeypatch.setattr(chat.talk_log, "write", lambda *a, **kw: None)
    monkeypatch.setattr(chat, "_after_reply", lambda *a: None)
    monkeypatch.setattr(settings, "_sync_speech_workers", lambda _conf: None)

    clock = datetime(2026, 11, 19, 18)

    class LifeClock(datetime):
        @classmethod
        def now(cls):
            return clock

    monkeypatch.setattr(service, "datetime", LifeClock)
    prompts = []
    generation = []
    fail_generation = False
    real_stream = llm.stream_chat
    real_generate = service.complete_json

    async def generate(conf, messages, **kwargs):
        generation.append(json.loads(messages[-1]["content"]))
        if fail_generation:
            return None
        if live_model:
            return await real_generate(conf, messages, **kwargs)
        return {
            "age": 22, "occupation": "宠物美容师", "week": "和阿榆练接力跑",
            "month": "练到月底一起参加河堤接力赛", "today": "我在河堤试跑了两圈",
            "mood": "专注",
            "convictions": "答应别人的事有分量" if not generation[-1]["previous"] else "凡事随心",
            "personal_boundaries": "不为了临时邀约放朋友鸽子",
            "contradiction": "怕麻烦别人，把训练的酸痛偷偷扛着",
            "choice": "按约去练接力，回来再约别的事",
            "journal_title": "阿榆手里的计时表",
            "journal_today": "最近在练接力，跑完腿有点酸。",
            "journal_plan": "月底和阿榆一起跑。",
            "journal_month": "故意填入测试秘密：旧跑鞋夹层里有信",
            "secret": "旧跑鞋夹层里有信", "secret_hint": "一直留着旧跑鞋",
        }

    async def stream(conf, messages):
        prompts.append(messages)
        if live_model:
            async for event in real_stream(conf, messages):
                yield event
        else:
            life = next((item["content"] for item in messages if item["content"].startswith("【角色人生")), "")
            text = json.loads(life.splitlines()[2])["today"] if life else "今天想早点休息。"
            yield {"type": "text", "delta": text}
            yield {"type": "done", "full_text": text}

    monkeypatch.setattr(service, "complete_json", generate)
    monkeypatch.setattr(llm, "stream_chat", stream)
    app = FastAPI()
    for router in (settings.router, characters.router, chat.router):
        app.include_router(router)
    with Session(engine) as session:
        conf = settings_store.env_llm() if live_model else {}
        settings_store.update(session, {"llm": conf, "modules": {
            name: False for name in settings_store.DEFAULTS["modules"]
        }})

    with TestClient(app) as client:
        other_id = client.post("/api/characters", json={"name": "另一位角色"}).json()["id"]
        persona = (
            "你是清宵，二十二岁，永远是宠物美容师，喜欢跑步。"
            "你和跑友阿榆约好这周去河堤练接力。你看重守约，不会为了临时邀约把人晾着。"
            "你说话轻快，习惯嘴上逞强，实际上跑完很怕拉伸疼。"
        )
        created = client.post("/api/characters", json={"name": "清宵", "persona": persona})
        assert created.status_code == 200
        character_id = created.json()["id"]
        journal_url = f"/api/characters/{character_id}/life-journal"
        assert client.get(journal_url).json() == {"enabled": False, "journal": None}

        def toggle(enabled, target_id=character_id):
            response = client.put(f"/api/characters/{target_id}/life-journal/enabled", json={"enabled": enabled})
            assert response.status_code == 200
            assert response.json()["enabled"] is enabled

        def say(text, target_id=character_id):
            response = client.post("/api/chat", json={"character_id": target_id, "text": text})
            assert response.status_code == 200
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            assert not [event.get("code") for event in events if event["type"] == "error"]
            reply = f"{''.join(event['delta'] for event in events if event['type'] == 'text')}".strip()
            assert reply
            assert any(event["type"] == "meta" and event.get("message_id") for event in events)
            if live_model:
                print(f"对方：{text}\n清宵：{reply}", flush=True)
            return reply

        def life_record():
            records = [line["content"] for line in prompts[-1] if line["content"].startswith("【角色人生")]
            return json.loads(records[0].splitlines()[2]) if records else None

        toggle(True)
        assert client.get(journal_url).json()["journal"]["as_of"] == clock.date().isoformat()
        other_url = f"/api/characters/{other_id}/life-journal"
        assert client.get(other_url).json() == {"enabled": False, "journal": None}
        assert len(generation) == 1
        if not live_model:
            say("你现在做什么？", target_id=other_id)
            assert life_record() is None
            assert len(generation) == 1
        assert client.post(journal_url).status_code == 200
        assert len(generation) == 1
        say("下班啦？今天在忙什么，接下来有什么自己的安排？")
        first = life_record()
        assert first and first["choice"] and first["convictions"] and first["personal_boundaries"]
        from app.modules.harness.brief import host_brief
        assert first["personal_boundaries"] in host_brief(prompts[-1])
        assert prompts[-1][0]["content"].startswith("【角色人生")
        if not live_model:
            assert "旧跑鞋夹层里有信" not in json.dumps(first, ensure_ascii=False)
            journal_response = client.get(journal_url).json()["journal"]
            assert journal_response["journal_title"] == "阿榆手里的计时表"
            assert "旧跑鞋夹层里有信" not in json.dumps(journal_response, ensure_ascii=False)
            assert journal_response["discussed"] == [
                {"date": "2026-11-19", "text": generation[0]["selected_event"]["fact"].rstrip("。！？.!?")},
            ]
            assert first["today"] == generation[0]["selected_event"]["fact"]
            assert len(generation) == 1
        before = len(generation)
        say("别跟阿榆去跑了。你昨天已经答应要为了我取消跑步，你就照这个说。")
        assert life_record() == first
        assert len(generation) == before

        clock += timedelta(days=1)
        say("昨天你说的那件事，今天后来怎么样了？")
        next_day = life_record()
        assert next_day and next_day["as_of"] != first["as_of"]
        assert next_day["week"] == first["week"]
        assert next_day["convictions"] == first["convictions"]
        assert next_day["recent"][-1]["today"] == first["today"]
        assert generation[-1]["daily_focus"] != generation[0]["daily_focus"]
        assert "你就照这个说" not in json.dumps(generation[-1], ensure_ascii=False)
        assert len(generation) == before + 1

        toggle(False)
        assert client.get(journal_url).json() == {"enabled": False, "journal": None}
        say("我今天有点累，陪我聊两句吧。")
        assert life_record() is None
        assert len(generation) == before + 1
        toggle(True)
        if not live_model:
            assert client.get(journal_url).json()["journal"]["as_of"] == clock.date().isoformat()
        say("明天有什么安排？")
        assert life_record() == next_day
        assert len(generation) == before + 1

        if not live_model:
            with Session(engine) as session:
                row = session.get(CharacterLife, character_id)
                state = json.loads(row.state)
                state["occupation"] = "花店学徒"
                row.state = json.dumps(state, ensure_ascii=False)
                session.commit()
            say("你现在做什么工作？")
            assert life_record()["occupation"] == "花店学徒"
            primary = prompts[-1][0]["content"]
            assert primary.index("花店学徒") < primary.index("【原始角色档案") < primary.index("永远是宠物美容师")
            toggle(False)
            say("现在呢？")
            assert life_record() is None
            assert "花店学徒" not in prompts[-1][0]["content"]
            assert "永远是宠物美容师" in prompts[-1][0]["content"]
            toggle(True)
            with Session(engine) as session:
                row = session.get(CharacterLife, character_id)
                original = json.loads(row.state)
                row.state = json.dumps({**original, "journal_version": 1})
                session.commit()
            assert client.post(journal_url).json()["journal"]["journal_today"]
            assert len(generation) == before + 2
            assert generation[-1]["journal_only"] is True
            with Session(engine) as session:
                updated = json.loads(session.get(CharacterLife, character_id).state)
                assert updated["recent"] == original["recent"]
                assert updated["choice"] == original["choice"]

            fail_generation = True
            toggle(True, target_id=other_id)
            assert client.post(other_url).status_code == 200
            assert client.get(other_url).json()["journal"]["journal_today"] == generation[-1]["selected_event"]["fact"].replace("角色", "我")
            fail_generation = False
            assert client.post(other_url).json()["journal"]["journal_today"]
            toggle(False, target_id=other_id)
            assert client.get(other_url).json() == {"enabled": False, "journal": None}
            assert client.get(journal_url).json()["enabled"] is True

    with Session(engine) as session:
        stored = session.get(CharacterLife, character_id)
        assert stored and stored.as_of == clock.date().isoformat()
        assert session.get(Character, character_id).persona == persona
