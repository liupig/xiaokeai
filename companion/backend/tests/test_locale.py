"""对话语言：整句才切换，口令跟语言包，英文分句不按 20 个字切。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.locale_pack import LangRe, detect_script, set_reply  # noqa: E402
from app.services.speech_split import SentenceSplitter  # noqa: E402


def test_detect_script_needs_a_whole_sentence():
    assert detect_script("你好呀今天过得怎么样") == "zh-CN"
    assert detect_script("hello there friend") == "en"
    assert detect_script("今日はいい天気だね") == "ja"
    assert detect_script("오늘 날씨가 정말 좋네요") == "ko"
    assert detect_script("ok") is None
    assert detect_script("stop") is None
    mixed = detect_script("这个 VRM 模型好看")
    assert mixed != "en"


def test_zh_draw_and_en_commands():
    set_reply("zh-CN")
    assert LangRe("tarot.one").search("抽一张")
    assert LangRe("tarot.hint").search("抽一张")
    set_reply("en")
    assert LangRe("ingress.cut").search("please stop")
    assert LangRe("roleplay.enter").search("be a teacher")
    assert LangRe("roleplay.exit").search("stop roleplay")
    assert LangRe("classify.dance").search("another dance")
    assert LangRe("tarot.one").search("draw a card")
    set_reply("ko")
    assert LangRe("tarot.one").search("한 장 뽑아")
    assert LangRe("classify.dance").search("춤춰 줘")
    assert LangRe("roleplay.exit").search("롤플레이 그만")


def test_english_split_keeps_words():
    sp = SentenceSplitter("en")
    text = "This is a reasonably long English sentence without any period in it at all"
    parts = sp.feed(text)
    blob = " ".join(parts)
    assert "reasonab" not in blob
    full = (blob + " " + " ".join(sp.flush())).strip()
    assert "reasonably" in full
    assert "sentence" in full
