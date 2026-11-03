"""识别体验：大类、子类配置、锁住之后下一眼才换规格。"""
import os

import pytest

from app.modules.sight import service
from app.modules.sight.catalog import kinds
from app.modules.sight.match import match


@pytest.fixture()
def fresh(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGHT_HOME", str(tmp_path))
    service.reload()
    service.reset()
    yield
    service.reset()


def test_catalog_has_the_five_kinds(fresh):
    found = {item.id: item for item in kinds()}
    assert set(found) == {"game", "music", "movie", "video", "work"}
    assert found["game"].configurable is True
    assert found["video"].configurable is True
    assert found["work"].configurable is True
    assert {item.id for item in found["video"].subs} >= {"bilibili", "xiaohongshu", "douyin", "youtube", "tiktok"}
    assert {item.id for item in found["work"].subs} >= {"code", "slides", "doc"}
    assert found["game"].sub("league") is not None
    assert found["music"].interval == 8
    assert found["movie"].interval == 12


def test_league_locks_on_this_look_and_the_next_look_uses_it(fresh):
    first = service.prepare("LeagueClientUx.exe", "League of Legends", "League of Legends")
    assert first.active is False
    brief = service.commit("LeagueClientUx.exe", "League of Legends", "League of Legends", "")
    assert brief.kind == "game"
    assert brief.sub == "league"
    assert brief.phase == "lobby"
    assert "大厅" in brief.handoff
    second = service.prepare("LeagueClientUx.exe", "League of Legends", "League of Legends")
    assert second.active is True
    assert second.phase == "lobby"
    assert "原文：" in second.prompt
    assert "不猜英雄名字" in second.prompt
    assert second.frames == 1
    assert service.interval() == 6


def test_opening_a_game_locks_before_the_first_look(fresh):
    assert service.hold_name("英雄联盟") is True
    order = service.prepare()
    assert order.active is True
    assert order.phase == "launch"
    assert "英雄联盟" in order.prompt
    service.commit("explorer.exe", "桌面", "桌面", "")
    assert service.prepare().phase == "launch"


def test_champion_select_fills_only_the_seen_name(fresh):
    service.commit("LeagueClientUx.exe", "League of Legends", "League of Legends", "")
    stayed = service.commit(
        "LeagueClientUx.exe",
        "League of Legends",
        "League of Legends",
        "阶段：团战\n局面：在打\n仍在：是",
    )
    assert stayed.phase == "lobby"
    seen = service.commit(
        "LeagueClientUx.exe",
        "League of Legends",
        "League of Legends",
        "画面：一圈英雄头像\n原文：选择你的英雄\n阶段：选英雄\n仍在：是",
    )
    assert seen.phase == "select"
    assert seen.slots["hero"] == "没看清"
    service.reset()
    service.commit("LeagueClientUx.exe", "League of Legends", "League of Legends", "")
    dotted = service.commit(
        "LeagueClientUx.exe",
        "League of Legends",
        "League of Legends",
        "阶段：选英雄。仍在。",
    )
    assert dotted.phase == "lobby"
    service.reset()
    service.commit("LeagueClientUx.exe", "League of Legends", "League of Legends", "")
    brief = service.commit(
        "LeagueClientUx.exe",
        "League of Legends",
        "League of Legends",
        "阶段：选英雄\n英雄：艾希\n仍在：是",
    )
    assert brief.phase == "select"
    assert brief.slots["hero"] == "艾希"
    assert "艾希" in brief.handoff
    assert "不要点评具体英雄" not in brief.handoff
    assert "具体英雄" in service.cue_rule()
    order = service.prepare()
    assert order.detail is True
    assert "英雄联盟" in order.prompt


def test_death_yes_moves_and_a_phase_line_blocks_a_later_yes(fresh):
    service.commit("League of Legends.exe", "League of Legends", "", "")
    service.commit("League of Legends.exe", "League of Legends", "", "画面：旁边有一排小兵\n阶段：对线\n仍在：是")
    dead = service.commit("League of Legends.exe", "League of Legends", "", "画面：画面变灰，写着等待复活\n原文：等待复活\n阶段：阵亡")
    assert dead.phase == "dead"
    service.reset()
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    stayed = service.commit(
        "LeagueClientUx.exe",
        "League of Legends",
        "",
        "阶段：仍在。\n选英雄：是。\n仍在：是",
    )
    assert stayed.phase == "lobby"


def test_empty_hero_stays_empty(fresh):
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    service.commit("LeagueClientUx.exe", "League of Legends", "", "画面：一圈英雄头像\n原文：选择你的英雄\n阶段：选英雄\n仍在：是")
    brief = service.commit("LeagueClientUx.exe", "League of Legends", "", "阶段：选英雄\n英雄：\n仍在：是")
    assert brief.slots["hero"] == "没看清"


def test_a_bare_phase_line_moves_forward_only(fresh):
    service.commit("League of Legends.exe", "League of Legends", "", "")
    assert service.current().phase == "load"
    order = service.prepare()
    assert "具体动作" in order.prompt
    assert "原文：" in order.prompt
    assert "只能写一个" not in order.prompt
    brief = service.commit("League of Legends.exe", "League of Legends", "", "画面：旁边有一排小兵\n阶段：对线")
    assert brief.phase == "lane"
    brief = service.commit("League of Legends.exe", "League of Legends", "", "正在打开")
    assert brief.phase == "lane"
    brief = service.commit("League of Legends.exe", "League of Legends", "", "阶段：大厅\n模式：大厅\n仍在：是")
    assert brief.phase == "lane"
    assert brief.slots["lane"] == "没看清"


def test_a_bare_phase_name_does_not_move_and_victory_does(fresh):
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    service.commit("LeagueClientUx.exe", "League of Legends", "", "阶段：组队\n仍在：是")
    assert service.current().phase == "lobby"
    service.commit("LeagueClientUx.exe", "League of Legends", "", "选英雄。\n仍在：是")
    assert service.current().phase == "lobby"
    service.commit("chrome.exe", "陪看记录", "陪看记录", "阶段：排队\n原文：胜利\n仍在：是")
    assert service.current().phase == "lobby"
    service.reset()
    service.commit("League of Legends.exe", "League of Legends", "", "")
    service.commit("League of Legends.exe", "League of Legends", "", "画面：旁边有一排小兵\n阶段：对线\n仍在：是")
    order = service.prepare()
    assert "原文：" in order.prompt
    assert "不要写别的" not in order.prompt
    assert order.frames >= 3
    brief = service.commit(
        "League of Legends.exe",
        "League of Legends",
        "",
        "阶段：选英雄\n原文：胜利\n画面：结算面板上是胜利\n仍在：是",
    )
    assert brief.phase == "score"
    assert brief.slots["result"] == "胜利"
    assert "胜利" in brief.handoff
    assert "选英雄" not in brief.handoff
    service.reset()
    service.commit("League of Legends.exe", "League of Legends", "", "")
    service.commit("League of Legends.exe", "League of Legends", "", "画面：旁边有一排小兵\n阶段：对线\n仍在：是")
    filmed = service.commit(
        "League of Legends.exe",
        "League of Legends",
        "",
        "第3张：胜利\n第4张：游戏胜利界面显示玩家排名",
    )
    assert filmed.phase == "score"
    assert filmed.slots["result"] == "胜利"
    assert "没看清" not in filmed.handoff


def test_leblanc_stays_with_her_through_the_match(fresh):
    service.commit("League of Legends.exe", "League of Legends", "", "")
    loading = service.commit(
        "League of Legends.exe",
        "League of Legends",
        "",
        "英雄：乐芙兰\n原文：源氏码 乐芙兰\n仍在：是",
    )
    assert loading.phase == "load"
    assert loading.slots["hero"] == "乐芙兰"
    assert "乐芙兰" in loading.handoff
    assert "没看清" not in loading.handoff
    lane = service.commit(
        "League of Legends.exe",
        "League of Legends",
        "",
        "画面：旁边有一排小兵\n局面：在清兵\n仍在：是",
    )
    assert lane.phase == "lane"
    assert lane.slots["hero"] == "乐芙兰"
    assert "乐芙兰" in lane.handoff
    assert "在清兵" in lane.handoff
    dead = service.commit(
        "League of Legends.exe",
        "League of Legends",
        "",
        "原文：返回于 14\n仍在：是",
    )
    assert dead.phase == "dead"
    assert "乐芙兰" in dead.handoff
    assert "返回于 14" in dead.handoff
    score = service.commit(
        "League of Legends.exe",
        "League of Legends",
        "",
        "第3张：胜利\n第4张：游戏胜利界面显示玩家排名",
    )
    assert score.phase == "score"
    assert score.slots["hero"] == "乐芙兰"
    assert score.slots["result"] == "胜利"
    service.reset()
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    stayed = service.commit("LeagueClientUx.exe", "League of Legends", "", "原文：胜利\n仍在：是")
    assert stayed.phase == "lobby"


def test_a_new_action_on_lane_is_what_she_hears(fresh):
    service.commit("League of Legends.exe", "League of Legends", "", "")
    order = service.prepare()
    assert "不猜英雄名字" in order.prompt
    assert "原文：" in order.prompt
    service.commit(
        "League of Legends.exe",
        "League of Legends",
        "",
        "英雄：乐芙兰\n画面：旁边有一排小兵\n局面：在清兵\n仍在：是",
    )
    traded = service.commit(
        "League of Legends.exe",
        "League of Legends",
        "",
        "画面：乐芙兰用锁链打中了对面\n仍在：是",
    )
    assert traded.phase == "lane"
    assert "锁链打中了对面" in traded.handoff
    assert "乐芙兰" in traded.handoff
    assert "在清兵" not in traded.handoff


def test_leblanc_lines_are_actually_handed_to_her(fresh):
    from app.modules.glance.along import quiet_line, same_scene
    from app.modules.glance.situation import Situation, parse_observation
    from app.modules.glance.watch import hollow_company

    steps = [
        ("英雄：乐芙兰\n原文：源氏码 乐芙兰\n仍在：是", "乐芙兰"),
        ("画面：旁边有一排小兵\n局面：在清兵\n仍在：是", "在清兵"),
        ("画面：乐芙兰用锁链打中了对面\n仍在：是", "锁链打中了对面"),
        ("第1张：游戏设置窗口正在显示网络流量统计\n第5张：团战正在激烈进行", "团战"),
        ("原文：返回于 14\n仍在：是", "返回于 14"),
        ("第3张：胜利\n第4张：游戏胜利界面显示玩家排名", "胜利"),
    ]
    service.commit("League of Legends.exe", "League of Legends", "League of Legends", "")
    heard = []
    for text, needle in steps:
        brief = service.commit("League of Legends.exe", "League of Legends", "League of Legends", text)
        sit = Situation()
        obs = parse_observation(brief.handoff, source="screen")
        offer = sit.ingest(obs)
        assert offer is not None
        said = offer.summary
        assert needle in said
        if needle == "团战":
            assert "网络" not in said
        assert "没看清" not in said
        assert quiet_line(said) is False
        assert hollow_company(said) is False
        if heard:
            assert same_scene(heard[-1], said) is False
        heard.append(said)
        from app.modules.glance.watch import along_turn
        from app.modules.sight.service import bound_speech

        told = bound_speech(along_turn())
        assert f"这一句：「{said}」" in told
        assert needle in told


def test_match_process_moves_forward_and_not_backward(fresh):
    service.commit("League of Legends.exe", "League of Legends", "", "")
    service.commit("League of Legends.exe", "League of Legends", "", "阶段：对线\n线路：中路\n局面：在清兵\n仍在：是")
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    assert service.current().phase == "lane"
    assert service.current().slots["lane"] == "中路"


def test_leaving_the_client_unlocks(fresh):
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    service.commit("explorer.exe", "桌面", "", "")
    assert service.prepare().active is True
    service.commit("explorer.exe", "桌面", "", "")
    assert service.prepare().active is False
    assert service.cue_rule() == ""
    assert service.interval() is None


def test_still_no_unlocks_immediately(fresh):
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    brief = service.commit("LeagueClientUx.exe", "League of Legends", "", "阶段：大厅\n仍在：否")
    assert brief.active is True
    assert brief.phase == "lobby"
    brief = service.commit("explorer.exe", "桌面", "", "仍在：否")
    assert brief.active is False
    assert service.prepare().active is False


def test_two_looks_of_another_kind_switch(fresh):
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    service.commit("cursor.exe", "main.py - Cursor", "", "")
    assert service.current().kind == "game"
    service.commit("cursor.exe", "main.py - Cursor", "", "")
    assert service.current().kind == "work"
    assert service.current().sub == "code"
    order = service.prepare()
    assert order.scene == "code"
    assert order.detail is True


def test_video_platforms_and_a_browser_title_do_not_become_a_game(fresh):
    assert match("chrome.exe", "哔哩哔哩 (゜-゜)つロ 干杯", "").sub == "bilibili"
    assert match("msedge.exe", "小红书 - 你的生活指南", "").sub == "xiaohongshu"
    assert match("chrome.exe", "抖音", "").sub == "douyin"
    assert match("chrome.exe", "YouTube", "").sub == "youtube"
    assert match("chrome.exe", "TikTok - Make Your Day", "").sub == "tiktok"
    hit = match("chrome.exe", "League of Legends highlight", "")
    assert hit is None or hit.kind != "game"


def test_music_movie_and_slides(fresh):
    assert match("cloudmusic.exe", "", "").kind == "music"
    assert match("spotify.exe", "Spotify", "").sub == "spotify"
    assert match("vlc.exe", "a.mp4 - VLC", "").kind == "movie"
    assert match("powerpnt.exe", "季度汇报", "").sub == "slides"
    service.commit("vlc.exe", "a.mp4 - VLC", "", "")
    order = service.prepare()
    assert order.kind == "movie"
    assert order.frames == 3
    assert service.interval() == 12


def test_custom_game_sub_uses_the_template_and_can_be_removed(fresh):
    added = service.add_sub("game", {
        "id": "naraka",
        "label": "永劫无间",
        "names": ["永劫无间", "naraka"],
        "processes": ["NarakaBladepoint.exe"],
    })
    assert added["id"] == "naraka"
    assert service.hold_name("永劫无间") is True
    assert service.prepare().phase == "launch"
    service.reset()
    service.commit("narakaBladepoint.exe", "NARAKA", "", "")
    assert service.current().sub == "naraka"
    assert service.current().phase == "launch"
    with pytest.raises(service.SightError):
        service.remove_sub("game", "league")
    service.remove_sub("game", "naraka")
    assert match("narakabladepoint.exe", "NARAKA", "") is None


def test_a_sub_without_a_way_to_match_is_refused(fresh):
    with pytest.raises(service.SightError):
        service.add_sub("music", {"id": "radio", "label": "电台", "processes": ["radio.exe"]})
    with pytest.raises(service.SightError):
        service.add_sub("game", {"id": "blank", "label": "没有进程"})


def test_overlay_file_is_under_the_home(fresh, tmp_path):
    service.add_sub("video", {
        "id": "acfun",
        "label": "AcFun",
        "match": "title",
        "titles": ["acfun"],
    })
    assert (tmp_path / "subs.json").is_file()
    assert os.environ["SIGHT_HOME"] == str(tmp_path)
    assert match("chrome.exe", "AcFun", "").sub == "acfun"


def test_each_phase_has_its_own_company_and_the_surface_is_known(fresh):
    for kind in kinds():
        assert kind.subs
        for sub in kind.subs:
            assert sub.phases
            ids = [phase.id for phase in sub.phases]
            assert len(ids) == len(set(ids))
            for phase in sub.phases:
                assert phase.speak
                assert phase.company
                assert phase.say
    league = next(sub for sub in kinds()[0].subs if sub.id == "league")
    assert [phase.id for phase in league.phases] == [
        "launch", "lobby", "party", "queue", "select", "load", "shop", "leave", "lane", "fight", "dead", "score",
    ]
    client = match("qqmusic.exe", "QQ音乐", "")
    assert client.sub == "qqmusic"
    assert client.surface == "client"
    web = match("chrome.exe", "y.qq.com", "QQ音乐")
    assert web.sub == "qqmusic"
    assert web.surface == "web"
    assert match("chrome.exe", "music.youtube.com", "").sub == "youtubemusic"
    assert match("chrome.exe", "YouTube", "").sub == "youtube"
    assert match("哔哩哔哩.exe", "哔哩哔哩", "").surface == "client"
    assert match("chrome.exe", "bilibili.com", "").surface == "web"
    assert match("qyclient.exe", "爱奇艺", "").kind == "movie"
    assert match("msedge.exe", "v.qq.com", "").sub == "qqlive"
    assert match("msedge.exe", "v.qq.com", "").surface == "web"
    service.commit("LeagueClientUx.exe", "League of Legends", "", "")
    service.commit("League of Legends.exe", "League of Legends (TM)", "", "")
    assert service.current().phase == "load"
    assert "端：客户端" in service.current().handoff
    service.reset()
    service.commit("dnf.exe", "地下城与勇士", "", "")
    assert service.current().phase == "launch"
    service.reset()
    service.commit("chrome.exe", "y.qq.com", "", "")
    brief = service.commit("chrome.exe", "y.qq.com", "", "阶段：在听\n名字：晴天\n歌手：周杰伦\n仍在：是")
    assert brief.surface == "web"
    assert brief.slots["title"] == "晴天"
    assert "网页" in brief.handoff
    assert "不从歌词推断" in service.cue_rule()


def test_local_apps_for_each_language(fresh):
    assert service.hold_name("エルデンリング") is True
    assert service.current().sub == "elden"
    service.reset()
    assert service.hold_name("리그 오브 레전드") is True
    assert service.current().sub == "league"
    assert match("AppleMusic.exe", "Apple Music", "").sub == "applemusic"
    assert match("AppleMusic.exe", "Apple Music", "").surface == "client"
    assert match("chrome.exe", "music.apple.com", "").surface == "web"
    assert match("Melon.exe", "멜론", "").sub == "melon"
    assert match("genie.exe", "Genie", "") is None
    assert match("chrome.exe", "www.genie.co.kr", "").sub == "genie"
    assert match("chrome.exe", "music-flo.com", "").sub == "flo"
    assert match("chrome.exe", "music.line.me", "").sub == "linemusic"
    assert match("chrome.exe", "nicovideo.jp", "").sub == "niconico"
    assert match("chrome.exe", "chzzk.naver.com", "").sub == "chzzk"
    assert match("chrome.exe", "wavve.com", "").sub == "wavve"
    assert match("chrome.exe", "unext.jp", "").sub == "unext"
    assert match("chrome.exe", "primevideo.com", "").sub == "primevideo"
    assert match("chrome.exe", "Disney+ - YouTube", "").sub == "youtube"
    assert match("Hwp.exe", "문서", "").sub == "hangul"
    assert match("chrome.exe", "docs.google.com/presentation", "").sub == "gslides"
    assert match("chrome.exe", "docs.google.com/document", "").sub == "gdocs"
    assert match("VALORANT-Win64-Shipping.exe", "VALORANT", "").sub == "valorant"
    assert match("YuanShen.exe", "原神", "").sub == "genshin"
    assert match("GenshinImpact.exe", "原神", "").sub == "genshin"
    assert match("TslGame.exe", "PUBG", "").sub == "pubg"
    assert match("Twitch.exe", "Twitch", "").surface == "client"
