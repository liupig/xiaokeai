import asyncio

import pytest

from app.modules.sight import service
from app.modules.sight.media import inputs, title, update
from app.modules.sight.catalog import find_sub
from app.modules.glance.desktop import Desk
from app.modules.glance.situation import Situation, parse_observation
from app.modules.glance.media_session import choose


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGHT_HOME", str(tmp_path))
    service.reload()
    service.reset()
    yield
    service.reset()


@pytest.mark.parametrize("platform", ["网易云音乐", "爱奇艺", "Spotify", "腾讯视频", "YouTube", "抖音-记录美好生活"])
def test_platform_is_not_a_song_or_film_title(platform):
    assert title(platform) == ""


def test_movie_title_and_latest_subtitle_are_not_replaced_by_player_name():
    args = ("vlc.exe", "海上钢琴师 - VLC media player", "海上钢琴师 - VLC media player")
    service.commit(*args, "片名：海上钢琴师\n字幕：把东西给我放下")
    fresh = service.commit(*args, "字幕：船要开了\n画面：舱门打开")
    assert fresh.slots["title"] == "海上钢琴师"
    assert "标题：海上钢琴师" in fresh.handoff
    assert "把东西给我放下" not in fresh.handoff
    assert "船要开了" in fresh.handoff
    assert "标题：本地播放器" not in fresh.handoff


def test_music_keeps_artist_but_does_not_repeat_an_old_lyric():
    args = ("cloudmusic.exe", "夜曲 - 网易云音乐", "夜曲 - 网易云音乐")
    service.commit(*args, "歌名：夜曲\n歌手：周杰伦\n歌词：第一句歌词\n播放状态：playing")
    fresh = service.commit(*args, "歌词：第二句歌词\n播放状态：playing")
    assert fresh.slots["title"] == "夜曲"
    assert fresh.slots["artist"] == "周杰伦"
    assert "第一句" not in fresh.handoff and "第二句" in fresh.handoff
    changed = service.commit(*args, "歌名：晴天\n听到：旧歌没唱完的半句\n播放状态：playing")
    assert changed.slots["title"] == "晴天"
    assert changed.slots["artist"] == ""
    assert "旧歌" not in changed.handoff
    assert "内容切换" in changed.handoff


def test_pause_does_not_keep_delivering_lyrics_and_can_resume():
    args = ("spotify.exe", "Spotify", "Spotify")
    service.commit(*args, "歌名：夜曲\n歌词：旧歌词\n播放状态：playing")
    paused = service.commit(*args, "播放状态：paused")
    assert paused.phase == "paused"
    assert paused.slots["playback"] == "paused"
    assert "旧歌词" not in paused.handoff
    resumed = service.commit(*args, "播放状态：playing\n歌词：新的半句")
    assert resumed.phase == "playing"
    assert "新的半句" in resumed.handoff


def test_episode_and_cover_changes_clear_the_previous_scene():
    sub = find_sub("movie", "player")
    _, old = update(sub, "playing", {}, {"剧名": "某部剧", "集数": "第1集", "字幕": "旧台词"})
    _, fresh = update(sub, "playing", old, {"剧名": "某部剧", "集数": "第2集", "听到": "上一集声音"})
    assert fresh["内容切换"] == "是"
    assert "听到" not in fresh and "这一句" not in fresh
    music = find_sub("music", "spotify")
    _, old = update(music, "playing", {}, {"歌名": "同一首歌", "版本": "原版", "歌手": "甲", "歌词": "旧歌词"})
    _, fresh = update(music, "playing", old, {"歌名": "同一首歌", "版本": "翻唱", "歌手": "乙"})
    assert fresh["歌手"] == "乙" and "这一句" not in fresh


def test_seek_is_a_continuity_gap_not_a_plot_transition():
    sub = find_sub("movie", "player")
    _, old = update(sub, "playing", {}, {"片名": "某部电影", "播放位置": "100", "播放状态": "playing"})
    _, fresh = update(sub, "playing", old, {"播放位置": "20", "听到": "拖动之前的声音"})
    assert fresh["跳转"] == "是"
    assert "听到" not in fresh


def test_media_session_belongs_to_the_selected_app_and_browser_tab():
    rows = [{"app": "Spotify.exe", "title": "夜曲"}, {"app": "chrome.exe", "title": "另一条视频"}]
    desk = Desk(process="chrome.exe", title="当前这条 - YouTube", window="当前这条 - YouTube")
    assert choose(rows, desk) == {}
    assert choose(rows, Desk(process="spotify.exe"))["title"] == "夜曲"


def test_heard_dialogue_survives_the_sight_lock_without_becoming_visual_text():
    desk = Desk(process="vlc.exe", app="VLC", title="海上钢琴师", kind="movie")
    args = (desk.process, desk.title, desk.title)
    service.commit(*args, inputs(desk, "", ""))
    brief = service.commit(*args, inputs(desk, "画面：舱门打开", "船就要开了"))
    assert "船就要开了" in brief.handoff
    assert brief.slots["line_source"] == "audio"
    assert "船就要开了" not in inputs(desk, "", "船就要开了", echo=True)


def test_new_short_video_gets_a_new_object_and_no_previous_dialogue():
    args = ("chrome.exe", "YouTube", "YouTube")
    first = service.commit(*args, "标题：第一条\n字幕：旧视频内容")
    second = service.commit(*args, "标题：第二条\n字幕：新视频内容")
    sit = Situation()
    sit.ingest(parse_observation(first.handoff))
    old_object = sit.object_id
    sit.ingest(parse_observation(second.handoff))
    assert sit.object_id != old_object
    assert "旧视频" not in second.handoff


def test_ocr_does_not_promote_comments_or_playlists_to_subtitles():
    from app.modules.sight.media_ocr import facts

    lines = [{"text": "评论：太好看了", "words": [{"x": 300, "y": 800, "width": 300}]}]
    assert "字幕：" not in facts(lines, (1200, 1000), "video")
    assert "歌词：" not in facts(lines, (1200, 1000), "music")


@pytest.mark.parametrize("cue", ["b i n g . c o m / s e a r c h", "相 关 搜 索", "约 232,000 个结果", "扫码登录"])
def test_search_and_login_pages_override_hallucinated_video(cue):
    from app.modules.sight.media_ocr import combine
    rows = [{"text": cue}, {"text": "Q抖音正版官方", "words": [{"x": 400, "y": 800, "width": 150}]}]
    result = combine("画面：人物低头看屏幕，字幕显示陪看视频", rows, (1200, 1000), "video")
    assert "unavailable" in result
    assert "字幕：" not in result and "人物低头" not in result


def test_prompt_echo_is_not_evidence():
    from app.modules.sight.media_ocr import combine
    assert combine("画面：字幕显示陪看视频", [], (1200, 1000), "video") == ""


def test_recognized_action_reaches_the_real_offer_queue():
    import time
    from app.modules.glance.watch import WatchSession
    sit = Situation()
    watch = WatchSession(sit)
    stamp = time.time()
    watch.pulse(stamp)
    brief = service.commit("chrome.exe", "抖音", "抖音", "画面：男子背负沉重箱装艰难向上攀爬陡峭山崖。\n原文：翻山越岭回家的男人")
    obs = parse_observation(brief.handoff, timestamp=stamp)
    offer = watch.admit(obs, sit.ingest(obs))
    assert offer is not None
    assert "攀爬" in offer.summary or "翻山越岭" in offer.summary
    assert watch.candidate is not None


def test_static_actor_description_is_still_filtered():
    from app.modules.glance.situation import _caption
    assert _caption("一名戴眼镜的男子")


@pytest.mark.parametrize("action", [
    "身着蓝色衣物的男子坐在桌前，手放在桌上。",
    "人物侧身站立，手持长物，背景为古代街巷。",
    "女性在水中漂浮，眼神直视前方。",
])
def test_current_log_actions_reach_the_offer_queue(action):
    from app.modules.glance.watch import WatchSession
    brief = service.commit("chrome.exe", "抖音", "抖音", "画面：" + action)
    sit = Situation()
    watch = WatchSession(sit)
    obs = parse_observation(brief.handoff)
    offer = watch.admit(obs, sit.ingest(obs))
    assert offer is not None
    assert action.strip("。") in offer.summary
    assert watch.admit(obs, sit.ingest(obs)) is None


def test_more_company_request_resumes_speech_and_shortens_cadence():
    from app.modules.glance.watch import WatchSession
    from app.modules.glance.media_director import cadence
    watch = WatchSession()
    watch.user_says("别说话")
    assert watch.speak_locked
    watch.user_says("多陪我说说话")
    assert watch.situation.talk == "more"
    assert not watch.speak_locked
    assert cadence("video", elapsed=6, opening=False, talk="more", playback="playing")
    assert not cadence("video", elapsed=6, opening=False, talk="normal", playback="playing")
    assert not cadence("video", elapsed=60, opening=True, talk="more", playback="unavailable")


@pytest.mark.parametrize("echo", ["搜索页和登录页写播放状态：unavailable。", "搜索页和登录页：unavailable"])
def test_prompt_echo_does_not_block_real_media_action(echo):
    from app.modules.sight.media_ocr import combine
    text = combine(echo + "\n画面：男子坐在桌前，手放在桌上", [], (1200, 1000), "video")
    assert "unavailable" not in text
    brief = service.commit("chrome.exe", "抖音", "抖音", text)
    assert brief.slots.get("playback") != "unavailable"
    assert Situation().ingest(parse_observation(brief.handoff)) is not None


def test_empty_generation_retries_once_while_evidence_is_current():
    from app.modules.glance.game_director import grounded_reply
    calls = []

    async def model(config, messages):
        calls.append(messages)
        if len(calls) == 2:
            yield {"type": "text", "delta": "这绳子绕得还挺复杂，你觉得她能解开吗？"}

    answer = asyncio.run(grounded_reply({}, [], evidence="女子低头整理绳索", topic="video:1", scene="video", stream=model))
    assert len(calls) == 2
    assert answer["action"] == "speak"
    assert answer["attempts"][0]["errors"] == ["empty_reply"]


def test_explicit_silence_and_expired_evidence_do_not_retry():
    from app.modules.glance.game_director import grounded_reply
    calls = []

    async def model(config, messages):
        calls.append(messages)
        yield {"type": "text", "delta": "silent"}

    answer = asyncio.run(grounded_reply({}, [], evidence="女子低头整理绳索", topic="video:1", scene="video", stream=model))
    assert len(calls) == 1 and answer["action"] == "silent"
    calls.clear()
    answer = asyncio.run(grounded_reply({}, [], evidence="女子低头整理绳索", topic="video:1", scene="video", stream=model, valid=lambda: False))
    assert len(calls) == 1 and answer["action"] == "drop"
    assert answer["attempts"][0]["errors"] == ["candidate_expired"]


@pytest.mark.parametrize("text", [
    "画面：两名古装男子在室内对话，一人持刀处理肉\n天色尚暗",
    "第1张：天色尚暗",
    "人物在对话，面向另一方\n原文：当前字幕或歌词",
    "画面：当前人物正面对另一人进行对话",
    "人物坐在桌前，低头注视桌面物品；\n画面：当前人物在做什么、与什么互动，或场景中具体发生的事",
    "画面：中间人物手持纸袋与左侧人物交谈，背景有交易场景",
])
def test_latest_live_log_survives_full_media_pipeline(text):
    desk = Desk(process="chrome.exe", app="抖音", title="抖音精选电脑版 - 抖音旗下优质视频平台", kind="video")
    brief = service.commit(desk.process, desk.title, desk.title, inputs(desk, text, "The.", metadata={"status": "playing"}))
    sit = Situation()
    offer = sit.ingest(parse_observation(brief.handoff))
    assert offer is not None
    assert "当前字幕或歌词" not in offer.summary
    assert "当前字幕或歌词" not in brief.handoff


def test_copied_template_alone_cannot_become_a_remark():
    brief = service.commit("chrome.exe", "抖音", "抖音", "画面：当前人物在做什么、与什么互动，或场景中具体发生的事\n原文：当前字幕或歌词")
    assert Situation().ingest(parse_observation(brief.handoff)) is None


def test_held_media_point_can_retry_but_never_refreshes_capture_time(monkeypatch):
    import time
    from app.modules.glance import along
    from app.modules.glance.situation import Offer
    from types import SimpleNamespace

    now = time.time()
    point = Offer("video", "video:clip", "topic", now - 5, 1, "天色尚暗", max_age=18)
    state = along._State(on=True, held=point, held_trace="original-trace")
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "situation", SimpleNamespace(latest_object_id="video:clip"))
    monkeypatch.setattr(along, "live", SimpleNamespace(source_valid=True))
    offer, trace = along._take_held_offer()
    assert offer is point and trace == "original-trace"
    assert offer.observation_time == now - 5
    assert state.held is None
    state.held = point
    state.speaking = True
    assert along._take_held_offer() == (None, "")
    state.speaking = False
    point.observation_time = now - 30
    assert along._take_held_offer() == (None, "")
    assert state.held is None
    point.observation_time = now
    state.held = point
    along.situation.latest_object_id = "video:other"
    assert along._take_held_offer() == (None, "")
    assert state.held is None


def test_live_loop_requeues_a_visual_point_after_cadence_gap(monkeypatch):
    from app.modules.glance import league_mode
    monkeypatch.setattr(league_mode, "mode", lambda: "hybrid")
    import threading
    from types import SimpleNamespace
    from app.modules.glance import along, hearing, sense, trace
    from app.modules.glance.watch import WatchSession

    clock = [1000.0]
    sit = Situation()
    live = WatchSession(sit)
    state = along._State(on=True, greeted=True, spoke_at=1000)
    sight = {"kind": "video", "phase": "playing", "slots": {"playback": "playing"}}
    observations = iter([
        {"ok": True, "used_eyes": True, "observed_at": 1000, "trace_id": "visual-1", "sight": sight,
         "text": "界面：抖音\n类型：video\n画面：两名古装男子在室内对话，一人持刀处理肉"},
        {"ok": True, "skipped": True, "trace_id": "no-new-image", "sight": sight, "text": ""},
    ])
    marks = []
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "_halt", threading.Event())
    monkeypatch.setattr(along, "situation", sit)
    monkeypatch.setattr(along, "live", live)
    monkeypatch.setattr(along, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(along, "_last_model", 0)
    monkeypatch.setattr(along, "_modules_on", lambda: True)
    monkeypatch.setattr(along, "_live_holds_screen", lambda: False)
    monkeypatch.setattr(along, "_tarot_now", lambda cid: False)
    monkeypatch.setattr(hearing, "ear", SimpleNamespace(set_quiet=lambda value: None))
    monkeypatch.setattr(sense, "collect", lambda **kwargs: next(observations))
    monkeypatch.setattr(along, "_prepare_direct", lambda offer, _: offer)
    monkeypatch.setattr(service, "interval", lambda: 5)
    monkeypatch.setattr(trace, "mark", lambda item_id, **fields: marks.append((item_id, fields)))

    def advance(seconds):
        clock[0] += 13
        return bool(state.pending)

    monkeypatch.setattr(along, "_wait", advance)
    along._loop()
    assert "处理肉" in state.pending
    assert state.trace_id == "visual-1"
    assert state.offer.observation_time == 1000
    assert state.held is None
    assert any("保留这一眼" in fields.get("handoff_why", "") for _, fields in marks)


def test_web_video_subtitle_survives_browser_controls_and_reaches_character():
    from app.modules.sight.media_ocr import combine
    from app.modules.glance.media_director import bind_context
    rows = [
        {"text": "搜索", "words": [{"x": 300, "y": 140, "width": 100}]},
        {"text": "我不是师傅吗", "words": [{"x": 680, "y": 850, "width": 550}]},
        {"text": "4050", "words": [{"x": 1840, "y": 590, "width": 60}]},
        {"text": "评论：太好看了", "words": [{"x": 680, "y": 890, "width": 550}]},
    ]
    text = combine("画面：穿僧袍的人在林中抬手和坐在藤椅上的人交谈", rows, (1920, 1041), "video")
    brief = service.commit("chrome.exe", "抖音", "抖音", text)
    assert "我不是师傅吗" in brief.handoff
    assert "太好看了" not in brief.handoff
    sit = Situation()
    offer = sit.ingest(parse_observation(brief.handoff))
    assert offer is not None
    bind_context(offer, brief.public())
    assert "我不是师傅吗" in offer.summary
    assert "藤椅" in offer.summary


def test_visual_point_does_not_discard_subtitle_and_distinct_audio():
    from app.modules.glance.media_director import bind_context
    from app.modules.glance.situation import Offer
    import time
    brief = service.commit("chrome.exe", "抖音", "抖音", "画面：僧人指着坐在椅子上的人\n字幕：我不是师傅吗\n听到：那你怎么不听师傅的话")
    offer = Offer("video", "video:clip", "topic", time.time(), 1, "僧人指着坐在椅子上的人")
    bind_context(offer, brief.public())
    assert "指着" in offer.summary
    assert "我不是师傅吗" in offer.summary
    assert "那你怎么不听师傅的话" in offer.summary


def test_single_article_from_loopback_is_not_dialogue():
    from app.modules.glance.hearing import clean_heard
    assert clean_heard("The.") == ""
    assert clean_heard("The door is open.") == "The door is open."
    assert clean_heard("我不是师傅吗") == "我不是师傅吗"


def test_frozen_candidate_keeps_episode_and_action_with_subtitle():
    brief = service.commit("vlc.exe", "某剧 第12集", "某剧 第12集", "剧名：某剧 第12集\n字幕：这封信怎么在你手里\n画面：女子举着信封质问面前的人")
    sit = Situation()
    offer = sit.ingest(parse_observation(brief.handoff))
    assert offer is not None
    from app.modules.glance.media_director import bind_context
    bind_context(offer, brief.public())
    assert "第12集" in offer.summary
    assert "质问" in offer.summary


def test_lyrics_about_rain_do_not_prove_audible_rain():
    from app.modules.glance.media_director import unsupported_reply
    assert unsupported_reply("歌词：窗外的雨还没有停", "雨声听着还挺踏实")
    assert unsupported_reply("歌词：窗外的雨还没有停", "第一句就停在这里")
    assert unsupported_reply("歌词：窗外的雨还没有停", "这雨唱得还黏糊呢")


def test_tv_episode_uses_series_company_and_keeps_current_line():
    brief = service.commit("vlc.exe", "某剧 第12集", "某剧 第12集", "剧名：某剧 第12集\n字幕：门外有人")
    assert brief.slots["episode"] == "第12集"
    assert "这是电视剧" in brief.company
    assert "门外有人" in brief.handoff


def test_search_page_cannot_offer_a_fake_video_title():
    desk = Desk(process="chrome.exe", app="抖音", title="抖音 - 搜索", kind="video")
    text = inputs(desk, "画面：搜索结果页，尚未确认正在播放\n播放状态：unavailable", "")
    assert "标题：" not in text
    brief = service.commit("chrome.exe", "抖音 - 搜索", "抖音 - 搜索", text)
    assert brief.slots["playback"] == "unavailable"


def test_media_reaction_repairs_a_spoiler_before_voice(monkeypatch):
    from app.modules.glance.game_director import grounded_reply
    from app.services import llm

    calls = []

    async def model(config, messages):
        calls.append(messages)
        yield {"type": "text", "delta": "下一集他会死" if len(calls) == 1 else "这句听得我心里一紧。"}

    monkeypatch.setattr(llm, "stream_chat", model)
    answer = asyncio.run(grounded_reply({}, [], evidence="他在舱门口说再见", topic="movie:1", scene="movie"))
    assert len(calls) == 2
    assert answer["action"] == "speak"
    assert "下一集" not in answer["text"]


def test_late_asr_result_is_discarded_after_source_switch(monkeypatch):
    from app.modules.glance.hearing import Ear
    from app.modules.glance import hearing
    from app.services import asr

    ear = Ear()
    ear.bind("old-song")
    monkeypatch.setattr(hearing, "_record_span", lambda *args: b"wav")

    def transcribe(wav):
        ear.bind("new-song")
        return "旧歌的一句词"

    monkeypatch.setattr(asr, "transcribe", transcribe)
    assert ear._take(0.1) == ""
    assert ear.latest() == ""
