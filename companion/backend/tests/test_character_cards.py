"""角色卡 v2：世界书引擎、酒馆卡导入导出、prompt 层注入。"""
import base64
import io
import json

import pytest
from PIL import Image, PngImagePlugin

from app.modules.character import exporter as card_exporter
from app.modules.character import importer as card_importer
from app.modules.character import lorebook as lorebook_engine
from app.modules.character.card import (
    LorebookEntry, compose_persona, compose_user_persona, dump_lorebook,
    parse_lorebook,
)
from app.services import prompt_stack


def entry(**kw) -> LorebookEntry:
    base = dict(keys=["剑"], content="默认内容", order=100)
    base.update(kw)
    return LorebookEntry(**base)


class TestLorebook:
    def test_keyword_hit_and_case_insensitive(self):
        got = lorebook_engine.scan([entry(content="青霜剑是师父所留")], "你那把剑哪来的", [])
        assert got == ["青霜剑是师父所留"]

    def test_case_sensitive_flag(self):
        e = entry(keys=["OK"], case_sensitive=True, content="S")
        assert lorebook_engine.scan([e], "say ok please", []) == []
        assert lorebook_engine.scan([e], "say OK please", []) == ["S"]
        e2 = entry(keys=["OK"], case_sensitive=False, content="S")
        assert lorebook_engine.scan([e2], "say ok please", []) == ["S"]

    def test_prevent_and_exclude_recursion(self):
        first = entry(keys=["剑"], content="青霜", order=1)
        blocked = entry(keys=["青霜"], content="不该出", order=2, prevent_recursion=True)
        assert lorebook_engine.scan([first, blocked], "剑", []) == ["青霜"]

        a = entry(keys=["剑"], content="青霜", order=1)
        b = entry(keys=["青霜"], content="XYZ", order=2, exclude_recursion=True)
        c = entry(keys=["XYZ"], content="链尾", order=3)
        got = lorebook_engine.scan([a, b, c], "剑", [], max_depth=3)
        assert got == ["青霜", "XYZ"]  # b 的内容不喂下一轮，c 不触发

        b2 = entry(keys=["青霜"], content="XYZ", order=2)
        got2 = lorebook_engine.scan([a, b2, c], "剑", [], max_depth=3)
        assert "链尾" in got2

    def test_no_hit_returns_nothing(self):
        assert lorebook_engine.scan([entry()], "今天天气不错", []) == []

    def test_hit_uses_recent_history(self):
        history = [{"role": "user", "content": "剑还在吗"}]
        got = lorebook_engine.scan([entry()], "在", history)
        assert got == ["默认内容"]

    def test_constant_always_injected(self):
        e = entry(keys=[], constant=True, content="世界观：大胤王朝")
        assert lorebook_engine.scan([e], "无关话题", []) == ["世界观：大胤王朝"]

    def test_selective_requires_secondary_key(self):
        e = entry(keys=["雨"], selective=True, selective_keys=["江南"], content="她怕雨夜")
        assert lorebook_engine.scan([e], "下雨了", []) == []
        assert lorebook_engine.scan([e], "江南又下雨了", []) == ["她怕雨夜"]

    def test_order_sorting(self):
        a = entry(keys=["x"], content="A", order=200)
        b = entry(keys=["x"], content="B", order=10)
        assert lorebook_engine.scan([a, b], "x", []) == ["B", "A"]

    def test_disabled_skipped(self):
        e = entry(content="D", enabled=False)
        assert lorebook_engine.scan([e], "剑", []) == []

    def test_regex_keyword(self):
        e = entry(keys=["/第[一二三]章/"], content="章回设定")
        assert lorebook_engine.scan([e], "第三章开始了", []) == ["章回设定"]

    def test_recursive_trigger(self):
        sword = entry(keys=["剑"], content="那把剑叫青霜", order=1)
        frost = entry(keys=["青霜"], content="青霜剑封存着上古剑意", order=2)
        got = lorebook_engine.scan([sword, frost], "剑", [])
        assert "青霜剑封存着上古剑意" in got

    def test_total_chars_cap(self):
        big = entry(content="字" * 2000, order=1)
        small = entry(keys=["剑"], content="小条目", order=2)
        got = lorebook_engine.scan([big, small], "剑", [], max_total_chars=100)
        assert got == ["小条目"]


class TestCardCompose:
    def _char(self, **kw):
        class Fake:
            pass
        c = Fake()
        c.persona = kw.get("persona", "你是清宵。")
        c.personality = kw.get("personality", "")
        c.scenario = kw.get("scenario", "")
        c.mes_example = kw.get("mes_example", "")
        return c

    def test_compose_only_persona(self):
        assert compose_persona(self._char()) == "你是清宵。"

    def test_compose_with_sections(self):
        text = compose_persona(self._char(
            personality="冷傲", scenario="雪夜客栈", mes_example="<START>"))
        assert text.startswith("你是清宵。")
        assert "# 性格\n冷傲" in text
        assert "# 场景\n雪夜客栈" in text
        assert "# 对话示例" in text

    def test_user_persona_disabled(self):
        assert compose_user_persona({"enabled": False, "description": "x"}) == ""
        assert compose_user_persona(None) == ""
        assert compose_user_persona({"enabled": True}) == ""

    def test_user_persona_text(self):
        text = compose_user_persona(
            {"enabled": True, "name": "阿黎", "description": "程序员，养猫。"})
        assert "阿黎" in text and "程序员" in text

    def test_lorebook_roundtrip(self):
        entries = [entry(keys=["a", "b"], content="C", position="before_hist", order=5)]
        again = parse_lorebook(dump_lorebook(entries))
        assert again[0].keys == ["a", "b"]
        assert again[0].position == "before_hist"
        assert again[0].order == 5
        assert parse_lorebook("not json") == []

    def test_after_char_position(self):
        raw = {"keys": ["x"], "content": "c", "position": "after_char"}
        e = parse_lorebook(json.dumps([raw], ensure_ascii=False))[0]
        assert e.position == "after_char"
        raw2 = {"keys": ["x"], "content": "c", "position": 2}
        e2 = parse_lorebook(json.dumps([raw2]))[0]
        assert e2.position == "after_char"


V2_CARD = {
    "spec": "chara_card_v2",
    "data": {
        "name": "沈清霜",
        "description": "你是沈清霜，冷面剑客。",
        "personality": "冷傲、护短",
        "scenario": "雪夜，破庙避雪。",
        "first_mes": "……你也是来避雪的？",
        "mes_example": "<START>\n用户：你好\n沈清霜：嗯。",
        "alternate_greetings": ["站住。", "雪大了。"],
        "character_book": {
            "entries": [
                {"keys": ["剑"], "content": "青霜剑是师门遗物", "enabled": True,
                 "constant": False, "selective": False, "keysecondary": [],
                 "insertion_order": 100, "position": 0},
            ],
        },
        "tags": ["古风", "剑客"],
        "creator": "tester",
        "character_version": "1.0",
        "extensions": {"keep_me": {"nested": True}},
    },
}


def _png_with_card(card: dict, key: str = "chara") -> bytes:
    payload = base64.b64encode(json.dumps(card, ensure_ascii=False).encode("utf-8"))
    info = PngImagePlugin.PngInfo()
    info.add_text(key, payload.decode("ascii"))
    img = Image.new("RGB", (64, 64), (120, 80, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=info)
    return buf.getvalue()


class TestImporter:
    def test_v2_json_direct(self):
        data = json.dumps(V2_CARD, ensure_ascii=False).encode("utf-8")
        card = card_importer.parse_card(data, "shen.json")
        assert card.name == "沈清霜"
        assert card.source_format == "tavern_v2"
        assert card.lorebook[0].content == "青霜剑是师门遗物"
        assert card.alternate_greetings == ["站住。", "雪大了。"]

    def test_v2_png(self):
        card = card_importer.parse_card(_png_with_card(V2_CARD), "shen.png")
        assert card.name == "沈清霜"
        assert card.source_format == "tavern_v2"

    def test_v3_png_uses_ccv3_key(self):
        v3 = {"spec": "chara_card_v3", "data": {
            "name": "V3角色", "description": "desc", "system_prompt": "额外指令",
            "first_mes": "hi",
        }}
        card = card_importer.parse_card(_png_with_card(v3, key="ccv3"), "v3.png")
        assert card.source_format == "tavern_v3"
        assert "额外指令" in card.description

    def test_v1_top_level(self):
        v1 = {"name": "老卡", "description": "v1描述", "first_mes": "开场"}
        card = card_importer.parse_card(json.dumps(v1).encode(), "old.png")
        assert card.source_format == "tavern_v1"
        assert card.first_mes == "开场"

    def test_missing_name_raises(self):
        with pytest.raises(card_importer.CardParseError):
            card_importer.parse_card(b'{"description": "x"}', "x.json")

    def test_png_without_card_raises(self):
        img = Image.new("RGB", (8, 8))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        with pytest.raises(card_importer.CardParseError):
            card_importer.parse_card(buf.getvalue(), "plain.png")

    def test_post_idat_text_chunk_is_found(self):
        """真生态站点的卡在图像数据后追加元数据，PIL 的 img.info 读不到，必须能解析。"""
        payload = base64.b64encode(
            json.dumps(V2_CARD, ensure_ascii=False).encode("utf-8"))
        img = Image.new("RGB", (8, 8))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        # 手动在 IEND 前插一个 tEXt（模拟写卡在 IDAT 之后）
        raw = bytearray(buf.getvalue())
        chunk_body = b"chara\x00" + payload
        import struct, zlib
        chunk = struct.pack(">I", len(chunk_body)) + b"tEXt" + chunk_body
        chunk += struct.pack(">I", zlib.crc32(b"tEXt" + chunk_body))
        iend = raw.rfind(b"IEND") - 4
        raw[iend:iend] = chunk
        card = card_importer.parse_card(bytes(raw), "late.png")
        assert card.name == "沈清霜"
        assert card.source_format == "tavern_v2"

    def test_v2_instruction_fields(self):
        """v2/v3 的 system_prompt / post_history_instructions / depth_prompt 都收。"""
        card = {
            "spec": "chara_card_v2",
            "data": {
                "name": "X",
                "description": "desc",
                "system_prompt": "额外系统指令",
                "post_history_instructions": "历史后提示",
                "depth_prompt": {"prompt": "深度4提示", "depth": 4},
                "first_mes": "hi",
            },
        }
        parsed = card_importer.parse_card(
            json.dumps(card, ensure_ascii=False).encode(), "x.png")
        assert "额外系统指令" in parsed.description
        assert "历史后提示" in parsed.mes_example
        assert "深度4提示" in parsed.mes_example

    def test_aicc_card(self):
        aicc = {
            "spec": "aicc_card", "spec_version": "1.0", "id": "x",
            "data": {
                "name": "Evelyn",
                "general_description": "{{char}} is a bright presence.",
                "appearance": "Red hair.",
                "personality": {
                    "core": "Outgoing.",
                    "behavior_rules": ["Never breaks character"],
                    "speech_style": {"tone": "warm", "register": "casual"},
                },
                "background_history": "You two met in college.",
                "world_setting_context": "Modern city.",
                "dialogue": {
                    "greetings": ["Hey {{user}}!", "Oh, it's you."],
                    "dialogue_examples": ["{{char}}: hi\n{{user}}: hello"],
                },
                "prompts": {"system_prompt": "Keep replies short."},
                "world": {"worldbook_entries": [
                    {"name": "Moon", "keys": ["moon", "luna"],
                     "secondary_keys": ["night"], "content": "{{char}} fears the moon.",
                     "position": "after_char", "constant": False, "enabled": True,
                     "extensions": {"priority": 9}},
                ]},
                "metadata": {"creator": "Miyukii", "version": "1.0", "tags": ["modern"]},
            },
        }
        card = card_importer.parse_card(
            json.dumps(aicc, ensure_ascii=False).encode(), "evelyn.png")
        assert card.source_format == "aicc"
        assert card.name == "Evelyn"
        # 宏替换
        assert "Evelyn is a bright presence." in card.description
        assert "Hey 对方!" in card.first_mes
        # 外貌进人设，性格/行为规则合并，背景+世界进场景
        assert "# 外貌\nRed hair." in card.description
        assert "Outgoing." in card.personality and "Never breaks character" in card.personality
        assert "tone: warm" in card.personality
        assert "college" in card.scenario and "Modern city." in card.scenario
        assert "Keep replies short." in card.description
        # 开场白变体 + 世界书映射
        assert card.alternate_greetings == ["Oh, it's you."]
        e = card.lorebook[0]
        assert e.keys == ["moon", "luna"] and e.selective and e.selective_keys == ["night"]
        assert e.position == "after_char" and e.order == 9 and e.comment == "Moon"
        assert "Evelyn fears the moon." in e.content
        assert card.creator == "Miyukii" and card.tags == ["modern"]

    def test_fields_mapping(self):
        card = card_importer.parse_card(
            json.dumps(V2_CARD, ensure_ascii=False).encode(), "s.json")
        fields = card_importer.card_to_character_fields(card)
        assert fields["persona"] == "你是沈清霜，冷面剑客。"
        assert fields["greeting"] == "……你也是来避雪的？"
        greetings = json.loads(fields["greetings"])
        assert greetings[0] == "……你也是来避雪的？"
        assert len(greetings) == 3
        assert json.loads(fields["tags"]) == ["古风", "剑客"]
        assert fields["source_format"] == "tavern_v2"
        assert fields["source_card"]


class TestExporter:
    def _char(self, **kw):
        class Fake:
            pass
        c = Fake()
        defaults = dict(
            name="沈清霜", persona="你是沈清霜，冷面剑客。", personality="冷傲",
            scenario="雪夜", greeting="……你也是来避雪的？",
            greetings=json.dumps(["……你也是来避雪的？", "站住。"], ensure_ascii=False),
            mes_example="", lorebook=dump_lorebook(
                [LorebookEntry(keys=["剑"], content="青霜剑是师门遗物")]),
            tags=json.dumps(["古风"], ensure_ascii=False),
            creator="tester", card_version="1.0",
            source_format="tavern_v2",
            source_card=json.dumps(V2_CARD, ensure_ascii=False),
            avatar_path="",
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(c, k, v)
        return c

    def test_roundtrip_preserves_unknown_fields(self):
        card = card_exporter.card_json_from_character(self._char())
        assert card["spec"] == "chara_card_v2"
        assert card["data"]["extensions"]["keep_me"]["nested"] is True
        assert card["data"]["name"] == "沈清霜"
        assert card["data"]["character_book"]["entries"][0]["keys"] == ["剑"]

    def test_export_to_tavern_entry_shape(self):
        card = card_exporter.card_json_from_character(self._char())
        e = card["data"]["character_book"]["entries"][0]
        assert e["position"] == 0
        assert "keysecondary" in e and "insertion_order" in e

    def test_native_card_without_source(self):
        char = self._char(source_card="", source_format="native", creator="")
        card = card_exporter.card_json_from_character(char)
        assert card["spec"] == "chara_card_v2"
        assert card["data"]["creator"] == ""
        assert card["data"]["first_mes"] == "……你也是来避雪的？"
        assert card["data"]["alternate_greetings"] == ["站住。"]

    def test_export_png_bytes_parseable(self):
        png = card_exporter.export_png_bytes(self._char())
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        with Image.open(io.BytesIO(png)) as img:
            payload = base64.b64decode(img.info["chara"]).decode("utf-8")
        card = json.loads(payload)
        assert card["data"]["name"] == "沈清霜"


class TestPromptStackLayers:
    def _base_kwargs(self, **kw):
        defaults = dict(
            persona="你是清宵。", char_name="清宵",
            motion_groups={"dance": ["a.vmd"]},
            history=[{"role": "user", "content": "你好"}],
            user_text="你好", mode="user", last_at=None, character_id=0,
            boundary="strict",
        )
        defaults.update(kw)
        return defaults

    def test_lorebook_and_persona_layers(self):
        msgs = prompt_stack.build_messages(**self._base_kwargs(
            lorebook_before_char=["设定一"],
            lorebook_before_hist=["设定二"],
            user_persona="和你说话的人叫阿黎。",
        ))
        system = [m["content"] for m in msgs if m["role"] == "system"]
        joined = "\n".join(system)
        assert "设定一" in joined
        assert "设定二" in joined
        assert "阿黎" in joined
        # before_char 的设定在人设层之后、上下文层之前
        persona_idx = system.index("你是清宵。")
        lore_idx = next(i for i, c in enumerate(system) if "设定一" in c)
        ctx_idx = next(i for i, c in enumerate(system) if "【本轮上下文】" in c)
        assert persona_idx < lore_idx < ctx_idx

    def test_without_new_layers_unchanged_shape(self):
        msgs = prompt_stack.build_messages(**self._base_kwargs())
        system = [m for m in msgs if m["role"] == "system"]
        assert system[0]["content"] == "你是清宵。"
