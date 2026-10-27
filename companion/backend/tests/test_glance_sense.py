"""窗口文字和听到的句子怎么决定要不要再叫眼睛。"""
from app.modules.glance.desktop import Desk, differ
from app.modules.glance.hearing import clean_heard
from app.modules.glance.sense import render, should_call_eyes
from app.modules.glance.situation import parse_observation
from app.modules.glance.situation import Situation


def test_same_picture_is_not_a_change_and_a_miss_is_unknown():
    assert differ(1, 1) is False
    assert differ(0, 1) is False
    assert differ(0, 0xFFFF) is True
    assert differ(None, 3) is True
    assert differ(3, None) is None


def test_code_with_text_does_not_call_the_eyes():
    assert should_call_eyes("code", body=True, named=True, heard=False, motion="moved", force=True, find=False) is False
    assert should_call_eyes("code", body=False, named=True, heard=False, motion="moved", force=False, find=False) is False
    assert should_call_eyes("code", body=False, named=True, heard=False, motion="same", force=True, find=False) is True
    assert should_call_eyes("code", body=False, named=True, heard=False, motion="switched", force=False, find=False) is True


def test_a_song_with_a_title_or_lyric_skips_the_eyes():
    assert should_call_eyes("music", body=False, named=True, heard=False, motion="moved", force=True, find=False) is False
    assert should_call_eyes("music", body=False, named=False, heard=True, motion="moved", force=True, find=False) is False
    assert should_call_eyes("music", body=False, named=False, heard=False, motion="same", force=True, find=False) is True


def test_a_still_movie_is_looked_at_again_on_the_long_interval():
    assert should_call_eyes("movie", body=False, named=True, heard=True, motion="same", force=False, find=False) is False
    assert should_call_eyes("movie", body=False, named=True, heard=True, motion="same", force=True, find=False) is True
    assert should_call_eyes("movie", body=False, named=True, heard=False, motion="moved", force=False, find=False) is True


def test_finding_something_still_looks():
    assert should_call_eyes("code", body=True, named=True, heard=False, motion="same", force=False, find=True) is True


def test_a_new_subtitle_is_kept_when_the_last_frame_repeats():
    from app.modules.glance.sense import pick_line

    eyes = "第1张：风吹梅枝见了又晃\n第2张：梅娘给我带回来了\n"
    assert pick_line(eyes, "梅娘给我带回来了") == "风吹梅枝见了又晃"
    assert pick_line(eyes, "") == "梅娘给我带回来了"
    mixed = "第1张：这看似荒谬的旧俗曾存在过\n第2张：一位女性身着白色服装摆出姿势\n第3张：聊天窗口中有人在浏览消息\n"
    assert pick_line(mixed, "人类一直在寻找活下去的办法") == "这看似荒谬的旧俗曾存在过"


def test_film_subtitles_beat_a_heard_blip():
    desk = Desk(ok=True, app="Chrome", window="抖音-记录美好生活 - Google Chrome", title="抖音-记录美好生活", kind="video")
    eyes = "第1张：她背了我一路\n第2张：爹满山喊了一冬\n"
    text, channel = render(desk, "The.", eyes)
    assert channel == "screen"
    assert "原文：爹满山喊了一冬" in text
    assert "The." not in text
    obs = parse_observation(text)
    offer = Situation().ingest(obs)
    assert offer is not None
    assert "爹满山喊了一冬" in offer.summary
    assert "记录美好生活" not in offer.summary


def test_a_heard_line_replaces_a_misread_caption():
    desk = Desk(ok=True, app="PotPlayer", window="海上钢琴师 - PotPlayer", title="海上钢琴师", kind="movie")
    eyes = "界面：播放器\n类型：movie\n标题：海上钢琴师\n原文：看不清的一行字啊\n画面：舱门打开了\n变化：舱门打开了"
    text, channel = render(desk, "把东西给我放下", eyes)
    assert channel == "audio"
    assert "原文：把东西给我放下" in text
    assert "看不清" not in text
    assert "舱门打开了" in text
    obs = parse_observation(text)
    obs.channel = channel
    offer = Situation().ingest(obs)
    assert offer is not None
    assert offer.channel == "audio"
    assert "把东西给我放下" in offer.summary


def test_her_own_line_is_not_treated_as_a_lyric():
    desk = Desk(ok=True, app="网易云音乐", window="夜曲 - 网易云音乐", title="夜曲", kind="music")
    text, channel = render(desk, "这句词我认得", "", echo=["这句词我认得"])
    assert "这句词我认得" not in text
    assert channel == "window"
    assert "标题：夜曲" in text


def test_a_window_error_is_the_point():
    desk = Desk(
        ok=True,
        app="Cursor",
        window="engine.py - Cursor",
        title="engine.py",
        kind="code",
        texts=["NameError: glance_once"],
    )
    text, channel = render(desk, "", "")
    assert channel == "window"
    assert "类型：code" in text
    obs = parse_observation(text)
    obs.channel = channel
    offer = Situation().ingest(obs)
    assert offer is not None
    assert "NameError: glance_once" in offer.summary
    assert offer.channel == "window"


def test_editor_chrome_is_not_body_text():
    from app.modules.glance.desktop import _usable_text

    assert _usable_text("Chrome Legacy Window", "desktop.py - games", "desktop.py - games - Cursor") is False
    assert _usable_text("NameError: glance_once", "engine.py", "engine.py - Cursor") is True


def test_browser_and_player_names():
    from app.modules.glance.desktop import classify, short_title

    assert classify("cursor.exe", "engine.py - Cursor") == "code"
    assert classify("potplayer.exe", "海上钢琴师") == "movie"
    assert classify("chrome.exe", "猫开门 - YouTube") == "video"
    assert classify("cloudmusic.exe", "夜曲") == "music"
    assert short_title("engine.py - Cursor", "Cursor") == "engine.py"
    assert clean_heard("  <|zh|>把东西给我放下  ") == "把东西给我放下"
    assert clean_heard("…") == ""
