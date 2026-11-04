"""运行时体验测试：导入酒馆卡之后，按酒馆的玩法走一遍。

覆盖「玩起来」而不是「能导入」：
- 开场白由卡决定（first_mes），落库进历史，重复调用不重复说
- 开场白进历史：下一轮模型知道角色已经说过那句
- 聊关键词：世界书注入；换话题：不注入；回到话题：再注入
- 多轮之后 system 各层（人设/红线/用户档案）仍在，不随历史滚掉
- mes_example 里的 <START> 标记不会进 prompt
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

from app.models import Character, ChatMessage

from test_character_cards_api import TAVERN_V2, import_card, make_tavern_png


def history_rows(client, char_id: int) -> list[ChatMessage]:
    with Session(client.engine) as s:
        return list(s.exec(select(ChatMessage)
                           .where(ChatMessage.character_id == char_id)
                           .order_by(ChatMessage.id)).all())


def chat(client, char_id: int, text: str) -> str:
    resp = client.post("/api/chat", json={"character_id": char_id, "text": text})
    assert resp.status_code == 200, resp.text
    return resp.text


def system_text(client) -> str:
    return "\n".join(
        m["content"] for m in client.captured["messages"] if m["role"] == "system")


class TestGreeting:
    def test_greeting_spoken_once_and_persisted(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))
        r1 = api_client.post(f"/api/characters/{char.id}/greeting")
        assert r1.status_code == 200
        body = r1.json()
        assert body["spoken"] is True
        assert body["text"] == "……你也是来避雪的？"
        assert body["message_id"]

        rows = history_rows(api_client, char.id)
        assert len(rows) == 1
        assert rows[0].role == "assistant" and rows[0].kind == "welcome"

        # 幂等：再调一次不重复说、不重复插
        r2 = api_client.post(f"/api/characters/{char.id}/greeting")
        assert r2.json()["spoken"] is False
        assert len(history_rows(api_client, char.id)) == 1

    def test_greeting_falls_back_to_first_variant(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))
        char.greeting = ""
        with Session(api_client.engine) as s:
            row = s.get(Character, char.id)
            row.greeting = ""
            s.add(row)
            s.commit()
        body = api_client.post(f"/api/characters/{char.id}/greeting").json()
        assert body["text"] == "……你也是来避雪的？"

    def test_no_greeting_returns_unspoken(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))
        with Session(api_client.engine) as s:
            row = s.get(Character, char.id)
            row.greeting = ""
            row.greetings = "[]"
            s.add(row)
            s.commit()
        body = api_client.post(f"/api/characters/{char.id}/greeting").json()
        assert body["spoken"] is False


class TestMultiTurnExperience:
    def test_play_like_tavern(self, api_client):
        """按酒馆玩法连聊几轮：开场 → 聊设定 → 换话题 → 再回来 → 问我是谁。"""
        char = import_card(api_client, make_tavern_png(TAVERN_V2))

        # 1) 开场白由卡决定，并进历史
        api_client.post(f"/api/characters/{char.id}/greeting")

        # 2) 第一轮：聊「剑」，世界书注入；历史里已带开场白
        chat(api_client, char.id, "你那把剑是哪来的？")
        msgs = api_client.captured["messages"]
        system = system_text(api_client)
        assert "青霜剑是师门遗物" in system
        hist = [m["content"] for m in msgs if m["role"] != "system"]
        assert any("你也是来避雪的" in h for h in hist), "开场白没有进后续 prompt 的历史"
        # mes_example 的 <START> 被剥掉，不会进 prompt
        assert "<START>" not in system

        # 3) 换话题后，最近几轮历史里还有「剑」，设定延续注入（对齐酒馆的扫描窗口）
        chat(api_client, char.id, "今天雪好大，你冷不冷？")
        assert "青霜剑是师门遗物" in system_text(api_client), "话题延续时应继续注入"

        # 4) 连续三轮不相关的话题，「剑」滚出扫描窗口，不再注入；
        #    人设/用户档案/红线这些 system 常驻层不受影响
        chat(api_client, char.id, "那你围条围巾？")
        chat(api_client, char.id, "破庙里有火堆吗？")
        chat(api_client, char.id, "嗯，你也多穿点。")
        system = system_text(api_client)
        assert "青霜剑是师门遗物" not in system, "话题淡出后不应再注入"
        assert "你是沈清霜" in system
        assert "阿黎" in system
        assert "【尺度与拒绝口吻】" in system or "【底线与拒绝口吻】" in system

        # 5) 回到「剑」的话题，重新注入；问用户是谁，靠档案答得上
        chat(api_client, char.id, "我还是想知道那把剑的来历")
        system = system_text(api_client)
        assert "青霜剑是师门遗物" in system
        chat(api_client, char.id, "我叫什么来着？")
        assert "和你说话的人叫阿黎。" in system_text(api_client)

        # 落库：开场白 + 七轮问答
        rows = history_rows(api_client, char.id)
        assert rows[0].kind == "welcome"
        user_turns = [r for r in rows if r.role == "user"]
        assistant_turns = [r for r in rows if r.role == "assistant"]
        assert len(user_turns) == 7
        assert len(assistant_turns) == 8  # 开场白 1 + 回复 7

    def test_system_layers_survive_long_history(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))
        for i in range(6):
            chat(api_client, char.id, f"第{i}句闲聊")
        msgs = api_client.captured["messages"]
        system = [m["content"] for m in msgs if m["role"] == "system"]
        assert system[0].startswith("你是沈清霜")
        joined = "\n".join(system)
        assert "阿黎" in joined
        # 历史被裁剪但 system 全在（固定层每轮重拼）
        assert len(system) >= 4
