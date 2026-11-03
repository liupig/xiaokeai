"""Test the full text vocabulary, without claiming image-model accuracy."""
import pytest

from app.modules.sight.screen_text import champions, facts, hero_mentions, hero_name


@pytest.mark.parametrize("ident,item", list(champions().items()), ids=list(champions()))
def test_every_catalogue_hero_can_be_resolved_from_name_title_and_id(ident, item):
    for alias in (item["name"], item["title"], ident):
        mentions = hero_mentions(alias)
        assert ident in {mention["id"] for mention in mentions}
        assert hero_name(alias) == item["title"]
    text = facts([{"text": item["name"] + " " + item["title"]}])
    assert item["title"] in text
    assert not any(line.startswith("英雄：") for line in text.splitlines())


@pytest.mark.parametrize("text,hero", [
    ("已锁定：暗黑元首 辛德拉", "辛德拉"),
    ("你的英雄：疾风剑豪 亚索", "亚索"),
    ("玩家英雄：九尾妖狐 阿狸", "阿狸"),
    ("你已锁定：LeBlanc", "乐芙兰"),
])
def test_explicit_player_ownership_confirms_selection(text, hero):
    found = facts([{"text": text}])
    assert f"英雄：{hero}" in found
    assert "身份来源：ocr" in found


@pytest.mark.parametrize("text", [
    "队友已锁定：盖伦", "敌方已锁定：阿狸", "禁用英雄：亚索", "已锁定：尚未锁定辛德拉",
    "搜索英雄：辛德拉", "你的英雄：预选辛德拉", "聊天：我已锁定辛德拉", "我是乐芙兰高手",
])
def test_mentions_bans_search_and_nicknames_never_confirm_ownership(text):
    found = facts([{"text": text}])
    assert not any(line.startswith("英雄：") for line in found.splitlines())


def test_visible_enemy_does_not_replace_the_player():
    from app.modules.sight import service

    game = ("League of Legends.exe", "League of Legends", "League of Legends")
    service.reset()
    service.commit(*game, "")
    service.commit(*game, "英雄：乐芙兰\n画面：在清兵")
    seen = service.commit(*game, facts([{"text": "疾风剑豪 亚索"}]))
    assert seen.slots["hero"] == "乐芙兰"
    service.reset()


def test_one_character_names_with_skin_text_can_be_read_without_matching_blue():
    assert "Zed" in {x["id"] for x in hero_mentions("天煞 劫")}
    assert "Vi" not in {x["id"] for x in hero_mentions("蔚蓝色光效")}
