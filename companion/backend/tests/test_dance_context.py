from app.services.dance_context import build_dance_hint


CATALOG = [
    ("gokuraku-jodo.vmd", "极乐净土"),
    ("gokuraku-jodo-2p.vmd", "极乐净土（2P位）"),
    ("tomorrow.vmd", "Freely Tomorrow"),
]


def test_catalog_is_only_sent_for_dance_related_turns():
    assert build_dance_hint("晚上好", "", CATALOG) == ""
    hint = build_dance_hint("你会跳什么舞？推荐一支，先别跳。", "", CATALOG)
    assert "极乐净土" in hint
    assert "gokuraku-jodo.vmd" not in hint
    assert "这轮别输出" in hint
    assert "极乐净土" in build_dance_hint("你会跳什么？", "", CATALOG)


def test_named_dance_does_not_offer_a_random_replacement():
    hint = build_dance_hint("跳一下极乐净土。", "", CATALOG)
    assert '["极乐净土"]' in hint
    assert "Freely Tomorrow" not in hint
    assert "没有匹配" in build_dance_hint("跳一下不存在的舞。", "", CATALOG)


def test_dance_alias_and_followup_confirmation():
    assert "多个版本" in build_dance_hint("跳一段净土吧。", "", CATALOG)
    hint = build_dance_hint("就这支", "我推荐 Freely Tomorrow。", CATALOG)
    assert "确认" in hint and "Freely Tomorrow" in hint
    assert build_dance_hint("好的", "早点休息。", CATALOG) == ""
