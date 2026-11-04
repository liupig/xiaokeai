"""角色卡端到端：真实 HTTP 路由导入酒馆 PNG 卡 → Mock LLM 聊天一轮 → 导出回导。

夹具见 conftest.py（api_client）。语料级真卡压测见 test_tavern_corpus.py。
"""
from __future__ import annotations

import base64
import io
import json

from PIL import Image
from sqlmodel import Session, select

from app.models import Character, ChatMessage


TAVERN_V2 = {
    "spec": "chara_card_v2",
    "data": {
        "name": "沈清霜",
        "description": "你是沈清霜，冷面剑客。说话短，护短。",
        "personality": "冷傲、护短",
        "scenario": "雪夜，破庙避雪。",
        "first_mes": "……你也是来避雪的？",
        "mes_example": "<START>\n用户：你好\n沈清霜：嗯。",
        "alternate_greetings": ["站住。"],
        "character_book": {
            "entries": [
                {"keys": ["剑"], "content": "青霜剑是师门遗物，出鞘必见血。",
                 "enabled": True, "constant": False, "selective": False,
                 "keysecondary": [], "insertion_order": 100, "position": 0},
            ],
        },
        "tags": ["古风", "剑客"],
        "creator": "tester",
        "character_version": "1.0",
    },
}


def make_tavern_png(card: dict) -> bytes:
    payload = base64.b64encode(json.dumps(card, ensure_ascii=False).encode("utf-8"))
    from PIL import PngImagePlugin
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("chara", payload.decode("ascii"))
    img = Image.new("RGB", (64, 96), (90, 60, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=pnginfo)
    return buf.getvalue()


def import_card(client, data: bytes, name: str = "card.png") -> Character:
    resp = client.post(
        "/api/characters/import",
        files={"file": (name, data, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return Character(**resp.json())


class TestImportExportApi:
    def test_import_png_creates_character_with_cover(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))
        assert char.id and char.id > 0
        assert char.name == "沈清霜"
        assert char.persona.startswith("你是沈清霜")
        assert char.personality == "冷傲、护短"
        assert char.scenario == "雪夜，破庙避雪。"
        assert char.greeting == "……你也是来避雪的？"
        assert json.loads(char.greetings)[0] == "……你也是来避雪的？"
        assert json.loads(char.tags) == ["古风", "剑客"]
        assert char.creator == "tester"
        assert char.source_format == "tavern_v2"
        assert (char.avatar_path or "").startswith("char_")

        with Session(api_client.engine) as s:
            row = s.get(Character, char.id)
            entries = json.loads(row.lorebook or "[]")
            lore = {k: e["content"] for e in entries for k in e.get("keys", [])}
        assert lore["剑"] == "青霜剑是师门遗物，出鞘必见血。"

    def test_avatar_endpoint(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))
        resp = api_client.get(f"/api/characters/{char.id}/avatar")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/")
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_import_rejects_plain_png(self, api_client):
        img = Image.new("RGB", (8, 8))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        resp = api_client.post(
            "/api/characters/import",
            files={"file": ("plain.png", buf.getvalue(), "image/png")},
        )
        assert resp.status_code == 400

    def test_export_png_roundtrip(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))
        resp = api_client.get(f"/api/characters/{char.id}/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        blob = resp.content
        assert blob[:8] == b"\x89PNG\r\n\x1a\n"

        with Image.open(io.BytesIO(blob)) as img:
            card = json.loads(base64.b64decode(img.info["chara"]).decode("utf-8"))
        assert card["spec"] == "chara_card_v2"
        assert card["data"]["name"] == "沈清霜"
        assert card["data"]["description"].startswith("你是沈清霜")
        assert card["data"]["character_book"]["entries"][0]["keys"] == ["剑"]

        # 把导出的卡再导入：核心字段一致
        again = import_card(api_client, blob, name="shen_export.png")
        assert again.id != char.id
        assert again.name == char.name
        assert again.persona == char.persona
        assert json.loads(again.lorebook)[0]["content"] == "青霜剑是师门遗物，出鞘必见血。"


class TestChatPipelineWithImportedCard:
    def test_lorebook_and_user_persona_reach_llm(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))

        resp = api_client.post("/api/chat", json={
            "character_id": char.id, "text": "你那把剑是哪来的？",
        })
        assert resp.status_code == 200
        body = resp.text
        assert '"delta"' in body
        assert "嗯。" in body
        assert '"type": "meta"' in body

        messages = api_client.captured["messages"]
        system = [m["content"] for m in messages if m["role"] == "system"]
        joined = "\n".join(system)
        # 人设主层 + 酒馆字段拼的小节
        assert "你是沈清霜" in joined
        assert "# 性格\n冷傲、护短" in joined
        # 世界书命中注入
        assert "青霜剑是师门遗物" in joined
        # 用户档案注入
        assert "阿黎" in joined and "程序员" in joined
        # persona 仍是最前面的 system 层
        assert system[0].startswith("你是沈清霜")

        # 回复已落库
        with Session(api_client.engine) as s:
            rows = s.exec(select(ChatMessage)
                          .where(ChatMessage.character_id == char.id)
                          .order_by(ChatMessage.id)).all()
        assert [r.role for r in rows] == ["user", "assistant"]
        assert "嗯。" in rows[-1].full_content

    def test_lorebook_not_injected_without_keyword(self, api_client):
        char = import_card(api_client, make_tavern_png(TAVERN_V2))
        resp = api_client.post("/api/chat", json={
            "character_id": char.id, "text": "今天天气不错",
        })
        assert resp.status_code == 200
        messages = api_client.captured["messages"]
        joined = "\n".join(m["content"] for m in messages if m["role"] == "system")
        assert "青霜剑" not in joined
