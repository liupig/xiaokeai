"""陪玩记忆：原句钉、事件加权、偏好不衰减、摘要不挡事实。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.memory import rank  # noqa: E402
from app.modules.memory import service  # noqa: E402


def test_words_mark_a_fight_even_without_a_tag() -> None:
    name, level = rank.emotion_from_words("昨天用户和助手大吵了一架，用户气得想摔门")
    assert name == "angry"
    assert rank.emotion_peak(name, level) >= 0.5
    assert rank.emotion_from_words("用户喜欢下雨天") == ("", 0.0)


def test_small_talk_offers_are_not_stored() -> None:
    assert rank.allow_extracted("助手提议待会带用户去楼下买热奶茶", "open_loop", "今天风挺大的") is False
    assert rank.allow_extracted("助手告知用户闷了随时喊自己", "open_loop", "有点无聊") is False
    assert rank.allow_extracted(
        "助手答应下周带用户去看海，此事尚未完成",
        "open_loop",
        "你答应下周带我去看海，这事还没做完。",
    ) is True
    assert rank.allow_extracted(
        "助手答应下周带用户去看海，提议周末出发并询问想看日出还是日落，此事尚未完成",
        "open_loop",
        "你答应下周带我去看海，这事还没做完。",
    ) is False


def test_episode_follows_a_recalled_fact() -> None:
    rows = [{
        "id": "1",
        "summary": "昨天吵了一架，约定还没去看海",
        "key_events": [3, 4],
        "created_at": "2026-10-17T00:00:00",
    }]
    hit = rank.pick_episode_row(rows, "月亮升起来的时候那句原话是什么", fact_ids=["3"])
    assert hit and hit["id"] == "1"
    assert rank.pick_episode_row(rows, "今天午饭吃什么", fact_ids=[]) is None


def test_near_duplicate_fights_collapse() -> None:
    a = "用户昨天和对方大吵了一架，气得想摔门"
    b = "用户与对方昨天大吵了一架，气得想摔门"
    assert rank.same_memory(a, b) is True
    assert rank.same_memory(a, "用户喜欢下雨天，雨声能让自己安静下来") is False


def test_unrelated_chat_does_not_keep_a_weak_hit() -> None:
    assert rank.relevant_enough(0.25, "有点无聊", "用户喜欢下雨天，雨声能让自己安静下来") is False
    assert rank.relevant_enough(0.3, "我喜欢什么样的天气", "用户喜欢下雨天，雨声能让自己安静下来") is True
    assert rank.relevant_enough(0.5, "有点无聊", "用户喜欢下雨天") is True


def test_emotion_peak_ignores_calm_and_default_happy() -> None:
    assert rank.parse_emotion("[emo:happy]你好") == ("happy", 0.85)
    assert rank.emotion_peak("happy", 0.85) == 0.0
    assert rank.emotion_peak(*rank.parse_emotion("[emo:happy:1]")) == 1.0
    assert rank.emotion_peak(*rank.parse_emotion("[emo:sad]")) > 0
    assert rank.emotion_peak(*rank.parse_emotion("[emo:angry:0.4]")) == 0.4
    assert rank.emotion_peak(*rank.parse_emotion("[emo:neutral]")) == 0.0
    assert rank.emotion_peak(*rank.parse_emotion("[emo:relaxed:1]")) == 0.0
    assert rank.emotion_peak("", 0) == 0.0


def test_recency_half_life_and_event_score() -> None:
    now = datetime(2026, 10, 17, 12, 0, 0)
    assert rank.recency_score(now, now) == 1.0
    assert abs(rank.recency_score(now - timedelta(days=3), now) - 0.5) < 1e-6
    score = rank.event_score(0.4, 1, 0.8, 0.5)
    assert abs(score - (0.4 + 0.15 + 0.12 + 0.05)) < 1e-6


def test_pin_budget_drops_oldest() -> None:
    pins = [
        {"id": i, "content": f"句子{i}" + ("甲" * 120), "created_at": f"2026-01-0{i}T00:00:00"}
        for i in range(1, 6)
    ]
    kept = rank.select_message_pins(pins)
    ids = [row["id"] for row in kept]
    assert 1 not in ids
    assert ids == sorted(ids)
    assert len(ids) <= 4
    assert sum(len(row["content"]) for row in kept) <= 400


def test_assemble_keeps_room_for_preferences() -> None:
    pins = [{"id": "p", "content": "用户的名字是阿星"}]
    events = [{"id": f"e{i}", "content": f"事件{i}"} for i in range(6)]
    stable = [{"id": f"s{i}", "content": f"偏好{i}"} for i in range(6)]
    out = rank.assemble_facts(pins, events, stable)
    ids = [row["id"] for row in out]
    assert ids[0] == "p"
    assert len(out) == 8
    assert "s0" in ids
    assert "e5" not in ids


def test_episode_is_not_a_gate() -> None:
    rows = [
        {"id": "1", "summary": "一起听了雨", "created_at": "2026-10-01T00:00:00"},
        {"id": "2", "summary": "那天吵了一架还没和好", "created_at": "2026-10-10T00:00:00"},
    ]
    hit = rank.pick_episode_row(rows, "还在想吵架的事")
    assert hit and hit["id"] == "2"
    assert rank.pick_episode_row(rows, "今天吃什么") is None
    cue = rank.pick_episode_row(rows, "还记得吗")
    assert cue and cue["id"] == "2"


def test_preferences_ignore_recency_and_emotion() -> None:
    now = datetime(2026, 10, 17, 12, 0, 0)
    pool = [
        {
            "id": "old", "kind": "preference", "content": "喜欢猫",
            "_vector": 0.6, "importance": 0.5,
            "created_at": "2026-01-01T00:00:00",
            "emotion": "", "emotion_intensity": 0,
        },
        {
            "id": "new", "kind": "preference", "content": "喜欢狗",
            "_vector": 0.55, "importance": 0.5,
            "created_at": now.isoformat(),
            "emotion": "angry", "emotion_intensity": 1,
        },
    ]
    events, stable = service._split_scored(pool, now)
    assert events == []
    assert [row["id"] for row in stable] == ["old", "new"]
    assert stable[0]["_score"] == 0.6


def test_source_comes_from_the_window_not_the_model() -> None:
    window = [
        {"role": "user", "id": 10, "emotion": "", "emotion_intensity": 0},
        {"role": "assistant", "id": 11, "emotion": "sad", "emotion_intensity": 0.9},
    ]
    spec = service._coerce_extracted(
        {"text": "用户很伤心", "kind": "event", "n": 1, "source_message_id": 999},
        window,
    )
    assert spec is not None
    assert spec["source_message_id"] == 10
    assert spec["speaker"] == "user"
    assert spec["emotion"] == "sad"
    pref = service._coerce_extracted(
        {"text": "喜欢听雨", "kind": "preference", "n": 1, "emotion": "sad"},
        window,
    )
    assert pref is not None
    assert pref["emotion"] == ""


def test_store_rank_pin_and_inject(tmp_path: Path) -> None:
    from sqlmodel import Session, SQLModel, create_engine, select

    from app.models import ChatMessage, MemoryFact

    db = tmp_path / "mem.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    class _Mem:
        def __init__(self):
            self.hits = []

        def add(self, text, user_id=None, infer=False, metadata=None):
            return {"results": [{"memory": text, "metadata": metadata or {}}]}

        def search(self, *args, **kwargs):
            return {"results": self.hits}

        def get_all(self, **kwargs):
            return {"results": []}

        def delete(self, *args, **kwargs):
            return True

    mem = _Mem()
    orig = service._client
    service._client = lambda session: mem  # type: ignore[method-assign]
    service._cache["semantic"] = True
    try:
        with Session(engine) as session:
            service.upsert_fact(session, 1, kind="person", content="用户的名字是阿星", pinned=True)
            stored = service.store_extracted_facts(session, 1, [
                {
                    "text": "昨天吵了一架",
                    "kind": "event",
                    "speaker": "user",
                    "source_message_id": 3,
                    "emotion": "angry",
                    "emotion_intensity": 0.9,
                },
                {
                    "text": "喜欢听雨",
                    "kind": "preference",
                    "speaker": "user",
                    "source_message_id": 1,
                    "emotion": "happy",
                    "emotion_intensity": 1,
                },
                {
                    "text": "十天前去过公园",
                    "kind": "event",
                    "speaker": "assistant",
                    "source_message_id": 2,
                    "emotion": "happy",
                    "emotion_intensity": 0.85,
                },
                {
                    "text": "刚说的爱好",
                    "kind": "preference",
                    "emotion": "angry",
                    "emotion_intensity": 1,
                },
            ])
            assert len(stored) == 4
            facts = {row["content"]: row for row in service.list_facts(session, 1)}
            assert facts["昨天吵了一架"]["emotion"] == "angry"
            assert facts["昨天吵了一架"]["source_message_id"] == 3
            assert facts["喜欢听雨"]["kind"] == "preference"
            assert facts["喜欢听雨"]["emotion"] == ""
            assert facts["刚说的爱好"]["emotion"] == ""

            old = session.get(MemoryFact, int(facts["十天前去过公园"]["id"]))
            assert old is not None
            old.created_at = datetime(2026, 10, 7, 0, 0, 0)
            session.add(old)
            session.commit()

            by_text = {row.content: row for row in session.exec(select(MemoryFact)).all()}
            mem.hits = [
                {"memory": "昨天吵了一架", "score": 0.35, "metadata": {"sqlite_id": by_text["昨天吵了一架"].id}},
                {"memory": "喜欢听雨", "score": 0.88, "metadata": {"sqlite_id": by_text["喜欢听雨"].id}},
                {"memory": "十天前去过公园", "score": 0.62, "metadata": {"sqlite_id": by_text["十天前去过公园"].id}},
                {"memory": "刚说的爱好", "score": 0.5, "metadata": {"sqlite_id": by_text["刚说的爱好"].id}},
                {"memory": "无关的生气", "score": 0.1, "metadata": {"sqlite_id": 999}},
            ]
            low = service.store_extracted_facts(session, 1, [{
                "text": "无关的生气",
                "kind": "event",
                "emotion": "angry",
                "emotion_intensity": 1,
            }])
            assert low
            mem.hits[-1]["metadata"]["sqlite_id"] = int(low[0])

            picked = [row["content"] for row in service._retrieve(session, 1, "还在想昨天")]
            assert picked[0] == "用户的名字是阿星"
            assert "无关的生气" not in picked
            assert picked.index("昨天吵了一架") < picked.index("十天前去过公园")
            assert picked.index("喜欢听雨") < picked.index("刚说的爱好")

            for i, text in enumerate(["最早的一句", "第二句", "第三句", "第四句", "第五句"]):
                msg = ChatMessage(
                    character_id=1, role="user", content=text, kind="qa",
                    created_at=datetime(2026, 10, 1, 0, i, 0),
                )
                session.add(msg)
                session.commit()
                session.refresh(msg)
                service.pin_message(session, 1, int(msg.id))
            rp = ChatMessage(character_id=1, role="assistant", content="老师说你要交作业", kind="rp")
            session.add(rp)
            session.commit()
            session.refresh(rp)
            pinned_rp = service.pin_message(session, 1, int(rp.id))
            assert pinned_rp["kind"] == "rp"
            assert all(row["content"] != "老师说你要交作业" for row in service.list_facts(session, 1))

            service.save_episode(session, 1, "一起听了雨", [])
            service.save_episode(session, 1, "那天吵了一架还没和好", stored[:1])
            block = service.inject_memory(session, 1, [
                {"role": "system", "content": "人设"},
                {"role": "user", "content": "还在想吵架的事"},
            ])
            memory = block[1]["content"]
            assert "钉住的原句" in memory
            assert "第五句" in memory
            assert "最早的一句" not in memory
            assert "老师说你要交作业" in memory
            assert "扮演里钉住的原句" in memory
            assert "那天吵了一架还没和好" in memory
            assert "一起听了雨" not in memory
            assert "用户的名字是阿星" in memory
            assert "喜欢听雨" in memory
            quiet = service.inject_memory(session, 1, [
                {"role": "user", "content": "今天吃什么"},
            ])[0]["content"]
            assert "一起听了雨" not in quiet
            assert "那天吵了一架还没和好" not in quiet
            assert "喜欢听雨" in quiet
    finally:
        service._client = orig  # type: ignore[method-assign]
        service._cache["semantic"] = False
        engine.dispose()


if __name__ == "__main__":
    import tempfile

    test_words_mark_a_fight_even_without_a_tag()
    test_small_talk_offers_are_not_stored()
    test_episode_follows_a_recalled_fact()
    test_near_duplicate_fights_collapse()
    test_unrelated_chat_does_not_keep_a_weak_hit()
    test_emotion_peak_ignores_calm_and_default_happy()
    test_recency_half_life_and_event_score()
    test_pin_budget_drops_oldest()
    test_assemble_keeps_room_for_preferences()
    test_episode_is_not_a_gate()
    test_preferences_ignore_recency_and_emotion()
    test_source_comes_from_the_window_not_the_model()
    with tempfile.TemporaryDirectory() as folder:
        test_store_rank_pin_and_inject(Path(folder))
    print("ok")
