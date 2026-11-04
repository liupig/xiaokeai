"""TTS 输入归一化：省略号不能进合成。"""
from app.services.speech_split import sanitize_tts_text


def test_chinese_ellipsis_to_comma():
    got = sanitize_tts_text("是宁可把话说狠，也不肯先低头那点？……听起来还真有点耳熟。")
    assert "……" not in got
    assert got == "是宁可把话说狠，也不肯先低头那点？听起来还真有点耳熟。"


def test_ellipsis_mid_sentence():
    assert sanitize_tts_text("我想想……明天吧") == "我想想，明天吧"


def test_ellipsis_at_end():
    assert sanitize_tts_text("原来如此……") == "原来如此。"


def test_ascii_ellipsis():
    assert sanitize_tts_text("wait... what") == "wait， what"


def test_no_double_comma():
    assert sanitize_tts_text("嗯……，好吧") == "嗯，好吧"


def test_comma_before_period_collapses():
    assert sanitize_tts_text("原来如此……。") == "原来如此。"


def test_decimal_not_touched():
    assert sanitize_tts_text("圆周率是 3.14159") == "圆周率是 3.14159"


def test_plain_text_unchanged():
    assert sanitize_tts_text("你好呀，今天怎么样？") == "你好呀，今天怎么样？"


def test_empty():
    assert sanitize_tts_text("") == ""


def test_leading_ellipsis_removed():
    assert sanitize_tts_text("……听起来还真有点耳熟。") == "听起来还真有点耳熟。"
    assert sanitize_tts_text("……一什么，话都没说完就想糊弄我？") == "一什么，话都没说完就想糊弄我？"


def test_splitter_sanitizes_mirelle_lines():
    from app.services.speech_split import SentenceSplitter
    sp = SentenceSplitter("zh-CN")
    parts = sp.feed("去睡吧。……账先给你留着，人也给你留着。") + sp.flush()
    joined = "".join(parts)
    assert "……" not in joined, parts
    assert "账先给你留着，人也给你留着。" in joined

    sp2 = SentenceSplitter("zh-CN")
    parts2 = sp2.feed("没什么深奥的，就是“爱你一万年”被你咽回去半句。……我是说，你那句“爱你一”，后面卡壳了。") + sp2.flush()
    joined2 = "".join(parts2)
    assert "……" not in joined2, parts2
    assert "。我是说，你那句" in joined2
