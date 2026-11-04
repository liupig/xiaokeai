"""真卡语料压测：data/tmp/tavern_cards/*.png（aicharactercards.com 实卡）。

没有语料就跳过。每张卡走完整链路：导入 → 头像 → 导出 → 回导比对，
并统计真实生态的格式分布（v1/v2/v3、世界书条目、字段空缺率）。
有卡带世界书的，再抽一张走聊天管线验证注入。
"""
from __future__ import annotations

import base64
import io
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image
from sqlmodel import Session, select

from app.models import Character

CORPUS_DIR = Path(__file__).resolve().parents[1] / "data" / "tmp" / "tavern_cards"

STATS: dict = {
    "imported": 0,
    "specs": Counter(),
    "lorebook_cards": 0,
    "lorebook_entries": 0,
    "empty_description": 0,
    "empty_greeting": 0,
    "chat_lore_checked": 0,
}


def corpus_files() -> list[Path]:
    if not CORPUS_DIR.is_dir():
        return []
    return sorted(CORPUS_DIR.glob("*.png"))


FILES = corpus_files()
pytestmark = pytest.mark.skipif(not FILES, reason="没有真卡语料：先跑 data/tmp/tavern_cards/fetch_corpus.py")


def import_blob(client, blob: bytes, name: str) -> Character:
    resp = client.post("/api/characters/import", files={"file": (name, blob, "image/png")})
    assert resp.status_code == 200, resp.text
    return Character(**resp.json())


def export_blob(client, char_id: int) -> bytes:
    resp = client.get(f"/api/characters/{char_id}/export")
    assert resp.status_code == 200, resp.text
    return resp.content


def read_card_json(blob: bytes) -> dict:
    with Image.open(io.BytesIO(blob)) as img:
        payload = img.info.get("chara") or img.info.get("ccv3")
    assert payload, "导出卡缺 chara/ccv3 元数据"
    return json.loads(base64.b64decode(payload).decode("utf-8"))


@pytest.mark.parametrize("path", FILES, ids=[f.name for f in FILES])
def test_real_card_roundtrip(api_client, path: Path):
    blob = path.read_bytes()
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} 不是 PNG"

    char = import_blob(api_client, blob, path.name)
    # 基本字段：名字必有；允许 description 缺（生态里真有），但要能导入不崩
    assert char.name.strip(), f"{path.name} 导入后名字为空"
    STATS["imported"] += 1
    STATS["specs"][char.source_format] += 1
    if not (char.persona or "").strip():
        STATS["empty_description"] += 1
    if not (char.greeting or "").strip():
        STATS["empty_greeting"] += 1
    entries = json.loads(char.lorebook or "[]")
    if entries:
        STATS["lorebook_cards"] += 1
        STATS["lorebook_entries"] += len(entries)

    # 头像能取（导入 PNG 必留档）
    resp = api_client.get(f"/api/characters/{char.id}/avatar")
    assert resp.status_code == 200, f"{path.name} 头像取不到"

    # 导出 → 结构合法 → 回导一致
    out = export_blob(api_client, char.id)
    assert out[:8] == b"\x89PNG\r\n\x1a\n"
    card = read_card_json(out)
    assert card.get("spec") == "chara_card_v2", f"{path.name} 导出规格不对: {card.get('spec')}"
    assert card["data"]["name"] == char.name

    again = import_blob(api_client, out, f"re_{path.name}")
    assert again.name == char.name, f"{path.name} 回导名字变了"
    assert again.persona == char.persona, f"{path.name} 回导人设变了"
    assert json.loads(again.lorebook or "[]") == json.loads(char.lorebook or "[]"), \
        f"{path.name} 回导世界书变了"


def _plain_key(entries: list[dict]) -> str:
    for e in entries:
        for k in e.get("keys") or []:
            k = str(k).strip()
            # 挑一个普通词：非正则、无空白；CJK 单字也算（如「月」「剑」）
            has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in k)
            if (len(k) >= 2 or has_cjk) and not re.search(r"[/\\*\[\]{}()]", k) and " " not in k:
                return k
    return ""


@pytest.mark.parametrize("path", FILES, ids=[f"chat-{f.name}" for f in FILES])
def test_real_card_chat_lorebook(api_client, path: Path):
    char = import_blob(api_client, path.read_bytes(), path.name)
    entries = json.loads(char.lorebook or "[]")
    key = _plain_key(entries)
    if not key:
        pytest.skip("没有可用纯文本关键词")
    content = ""
    for e in entries:
        if key in [str(k) for k in (e.get("keys") or [])]:
            body = str(e.get("content") or "").strip()
            if body:
                content = body
                break
    if not content:
        pytest.skip("关键词命中的条目没有内容")

    # 命中：世界书内容要出现在给 LLM 的 system 里
    resp = api_client.post("/api/chat", json={
        "character_id": char.id, "text": f"我们聊聊{key}吧",
    })
    assert resp.status_code == 200, resp.text
    messages = api_client.captured["messages"]
    joined = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert content[:40] in joined, (
        f"{path.name}: 关键词「{key}」命中但世界书未注入"
    )
    # 人设主层仍然在最前（人设为空的卡不校验这条）
    if (char.persona or "").strip():
        system = [m["content"] for m in messages if m["role"] == "system"]
        assert system and system[0].startswith((char.persona or "").strip()[:20])
    STATS["chat_lore_checked"] += 1


def test_corpus_summary():
    """语料规模与生态分布统计（跑完上面单卡用例后看这里）。"""
    assert STATS["imported"] >= 20, f"语料不足：只成功导入 {STATS['imported']} 张"
    print("\n=== 真卡语料统计 ===")
    print(f"卡数: {STATS['imported']}")
    print(f"规格分布: {dict(STATS['specs'])}")
    print(f"带世界书: {STATS['lorebook_cards']} 张 / 共 {STATS['lorebook_entries']} 条")
    print(f"聊天注入验证: {STATS['chat_lore_checked']} 张")
    print(f"空人设: {STATS['empty_description']} / 空开场白: {STATS['empty_greeting']}")
