import asyncio

import pytest

from app.modules.sight import service
from app.modules.sight.media_ocr import facts, page_state
from app.modules.glance.situation import Situation, parse_observation
from app.modules.glance.watch import hollow_company


SAMPLES = [
    ("zh-CN", "字幕", "船就要开了，快上来", "某部剧 第12集", "歌手"),
    ("en", "Subtitles", "The ship is leaving. Come aboard.", "Our Story Episode 12", "Artist"),
    ("ja", "字幕", "船が出るよ、早く乗って", "物語 第12話", "アーティスト"),
    ("ko", "자막", "배가 곧 떠나요. 빨리 타세요.", "우리 이야기 제12화", "가수"),
]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGHT_HOME", str(tmp_path))
    service.reload()
    service.reset()
    yield
    service.reset()


@pytest.mark.parametrize("lang,label,line,title,artist", SAMPLES)
def test_all_four_scripts_reach_a_real_candidate(lang, label, line, title, artist):
    text = facts([{"text": f"{label}: {line}"}], (1200, 1000), "movie")
    assert line in text
    brief = service.commit("vlc.exe", title, title, f"标题：{title}\n{text}")
    assert brief.slots["line"] == line
    assert brief.slots["episode"]
    sit = Situation()
    offer = sit.ingest(parse_observation(brief.handoff))
    assert offer is not None
    assert line in offer.summary
    assert not hollow_company(line)


@pytest.mark.parametrize("cue", ["Search results", "Sign in to watch", "検索結果", "ログインして視聴", "검색 결과", "로그인 후 시청"])
def test_non_content_pages_in_all_languages(cue):
    assert page_state([{"text": cue}])


@pytest.mark.parametrize("status", ["paused", "一時停止", "일시정지"])
def test_pause_labels(status):
    brief = service.commit("vlc.exe", "Example", "Example", f"status: {status}\n字幕：船就要开了")
    assert brief.slots["playback"] == "paused"
    assert "船就要开了" not in brief.handoff


@pytest.mark.parametrize("text", ["In the next episode he will die.", "犯人は彼です", "다음 화에 죽어요", "The chorus sounds good", "雨音がいいね", "빗소리가 좋아요"])
def test_grounding_rules_cover_all_scripts(text):
    from app.modules.glance.media_director import unsupported_reply
    assert unsupported_reply("原文：Hello / こんにちは / 안녕하세요", text)


@pytest.mark.parametrize("lang,label,line,title,artist", SAMPLES)
def test_reply_language_is_user_preference_not_subtitle_language(monkeypatch, lang, label, line, title, artist):
    from app.locale_pack import set_reply
    from app.modules.glance.game_director import grounded_reply
    from app.modules.sight.media_language import reply_rule
    from app.services import llm
    captured = []

    async def model(config, messages):
        captured.extend(messages)
        yield {"type": "text", "delta": line}

    monkeypatch.setattr(llm, "stream_chat", model)
    set_reply(lang)
    try:
        result = asyncio.run(grounded_reply({}, [], evidence=line, topic="media:1", scene="movie"))
        assert result["action"] == "speak"
        assert any(m["role"] == "system" and m["content"] == reply_rule(lang) for m in captured)
    finally:
        set_reply("zh-CN")


@pytest.mark.parametrize("lang,expected", [("zh-CN", "mimo"), ("en", "mimo"), ("ja", "edge"), ("ko", "edge")])
def test_voice_route_does_not_use_chinese_preset_for_japanese_or_korean(lang, expected):
    from app.services.tts import language_route, resolve_voice
    from app.locale_pack import voice_fits
    engine, voice = language_route("mimo", lang)
    assert engine == expected
    if voice:
        assert voice_fits(engine, resolve_voice(engine, voice, voice), lang)


@pytest.mark.parametrize("quiet,resume", [("别说话", "可以说了"), ("Please be quiet.", "You can speak now."), ("静かにして", "話していいよ"), ("조용히 해줘", "이제 말해도 돼")])
def test_four_language_user_controls(quiet, resume):
    from app.modules.glance.watch import WatchSession
    sit = Situation()
    watch = WatchSession(sit)
    watch.user_says(quiet)
    assert watch.speak_locked and sit.talk == "quiet"
    watch.user_says(resume)
    assert not watch.speak_locked and sit.talk == "normal"


def test_native_ocr_still_reads_archived_search_page_on_windows():
    import os
    from pathlib import Path
    from PIL import Image
    from app.modules.sight.screen_text import _read_native as read
    path = Path(__file__).resolve().parents[1] / "data/glance-lab/2026-11-01/g20261101125147523-0006-c7.jpg"
    if os.name != "nt" or not path.exists():
        pytest.skip("Needs Windows OCR and the local archived screenshot")
    with Image.open(path) as image:
        rows = read(image)
    assert rows
    assert all(row.get("language") for row in rows)
    assert page_state(rows)
