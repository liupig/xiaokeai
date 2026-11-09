import asyncio
import time

from app.modules.glance.direct import direct_reply, enabled, parse_protocol
from app.modules.glance.media_director import cadence
from app.modules.glance.media_subtitles import SubtitleSampler, beat


def test_direct_switch_defaults_on_and_can_restore_legacy(monkeypatch):
    from app.modules.glance.direct import generator

    monkeypatch.delenv("XIAOKE_ALONG_DIRECT", raising=False)
    monkeypatch.delenv("XIAOKE_ALONG_DIRECT_GENERATOR", raising=False)
    assert enabled()
    assert generator() == "chat"
    monkeypatch.setenv("XIAOKE_ALONG_DIRECT", "0")
    assert not enabled()
    monkeypatch.setenv("XIAOKE_ALONG_DIRECT_GENERATOR", "minicpm")
    assert generator() == "minicpm"


def test_three_line_protocol_keeps_colons_in_the_speech():
    result = parse_protocol("情绪：搞笑\n值不值得说：说\n台词：这句反转：我真的没料到")
    assert result["action"] == "speak"
    assert result["text"] == "这句反转：我真的没料到"
    assert result["mood"] == "搞笑"


def test_protocol_failure_and_long_lines_stay_silent():
    assert parse_protocol("这句很好笑")["action"] == "protocol"
    assert parse_protocol("情绪：开心\n值不值得说：说\n台词：哈哈")["action"] == "protocol"
    assert parse_protocol("情绪：平静\n值不值得说：说\n台词：" + "很长" * 13)["action"] == "protocol"


def test_direct_generation_runs_once_and_maps_mood():
    calls = []

    async def model(config, messages):
        calls.append(messages)
        yield {"type": "text", "delta": "这句听着还挺暖的"}

    result = asyncio.run(direct_reply({}, [], evidence="门外有人，我回来了", stream=model))
    assert len(calls) == 1
    assert result["action"] == "speak"
    assert result["text"] == "这句听着还挺暖的"
    assert result["performance"] == [{"type": "emo", "value": "relaxed"}]


def test_explicit_silence_and_invalid_evidence_do_not_retry():
    calls = []

    async def silent(config, messages):
        calls.append(messages)
        yield {"type": "text", "delta": "不说"}

    result = asyncio.run(direct_reply({}, [], evidence="船要开了", stream=silent))
    assert result["action"] == "silent" and len(calls) == 1

    async def invented(config, messages):
        calls.append(messages)
        yield {"type": "text", "delta": "「他没说完的这句话」太虐了"}

    result = asyncio.run(direct_reply({}, [], evidence="船要开了", stream=invented))
    assert result["action"] == "unsupported" and not result["text"]
    assert len(calls) == 2


def test_duplicate_and_expired_lines_never_reach_playback():
    async def model(config, messages):
        yield {"type": "text", "delta": "这个反转我真的没料到"}

    result = asyncio.run(direct_reply({}, [], evidence="船要开了", recent=["这个反转我真的没料到啊"], stream=model))
    assert result["action"] == "duplicate"
    result = asyncio.run(direct_reply({}, [], evidence="船要开了", valid=lambda: False, stream=model))
    assert result["action"] == "drop" and not result["text"]


def test_repeated_clauses_are_duplicates_even_with_new_content_around_them():
    from app.modules.glance.direct import evaluate

    recent = ["黑块退，累不累？躺会儿。"]
    assert evaluate("标题下黑块退，累不累？躺会儿。", evidence="", recent=recent, kind="company")["action"] == "duplicate"
    assert evaluate("画面里烟雾飘，累不累？躺会儿。", evidence="", recent=recent, kind="company")["action"] == "duplicate"
    result = evaluate("这个反转真的没料到", evidence="", recent=recent, kind="company")
    assert result["action"] == "speak"


def test_unplayed_drafts_feed_generation_and_playback_guards(monkeypatch):
    from types import SimpleNamespace
    from app.modules.glance import along
    from app.modules.glance.situation import Offer

    text = "画面里烟雾飘，累不累？躺会儿。"
    offer = Offer("video", "video:clip", "new", time.time(), 1, "新画面", direct=True)
    state = along._State(on=True, offer=offer, trace_id="trace", drafts=["黑块退，累不累？躺会儿。", text])
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "live", SimpleNamespace(speeches=[]))
    monkeypatch.setattr("app.modules.glance.journal.journal.recent_lines", lambda: [])
    assert text in along._recent_lines()
    assert not along.generated(text, expected_trace="trace")
    assert state.generated == ""
    assert state.playback != "generated"

    fresh = "这个反转真的没料到"
    state.drafts[:] = [fresh]
    assert along.generated(fresh, expected_trace="trace")
    assert state.generated == fresh
    assert state.playback == "generated"


def test_subtitle_rows_merge_after_the_coalescing_window():
    sampler = SubtitleSampler()
    sampler._source = "movie"
    now = time.time()
    sampler._rows.extend([
        {"observed_at": now - 1, "ocr_text": "字幕：上一句"},
        {"observed_at": now, "ocr_text": "字幕：下一句"},
    ])
    assert sampler.drain("movie", coalesce=2) == []
    sampler._rows[0]["observed_at"] = now - 3
    rows = sampler.drain("movie", coalesce=2)
    assert beat(rows) == "上一句；下一句"
    assert sampler.drain("movie") == []
    assert beat(rows + rows) == "上一句；下一句"


def test_direct_cadence_has_shorter_hard_limits_without_changing_legacy():
    assert cadence("movie", elapsed=16, opening=False, talk="normal", playback="playing", direct=True)
    assert not cadence("movie", elapsed=16, opening=False, talk="normal", playback="playing")
    assert cadence("video", elapsed=9, opening=False, talk="normal", playback="playing", direct=True)
    assert not cadence("video", elapsed=9, opening=False, talk="normal", playback="playing")
    assert cadence("movie", elapsed=8, opening=False, talk="more", playback="playing", direct=True)


def _run_direct_loop(monkeypatch, generated=""):
    import threading
    from types import SimpleNamespace
    from app.modules.glance import along, hearing, sense
    from app.modules.glance.situation import Offer, Situation
    from app.modules.glance.watch import WatchSession
    from app.modules.sight import service as sight_service

    now = time.time()
    old = Offer("video", "video:clip", "old", now, 1, "旧字幕", direct=True)
    situation = Situation()
    watch = WatchSession(situation)
    state = along._State(
        on=True, character_id=1, greeted=True, spoke_at=now - 20,
        speaking=True, speak_since=now, pending="旧字幕", offer=old,
        generated=generated, playback="generated" if generated else "queued",
    )
    found = {
        "ok": True, "used_eyes": False, "observed_at": now, "trace_id": "new-trace",
        "text": "原文：新的一句字幕", "subtitle_beat": "新的一句字幕",
        "sight": {"kind": "video", "phase": "playing", "slots": {"playback": "playing"}},
    }
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "situation", situation)
    monkeypatch.setattr(along, "live", watch)
    monkeypatch.setattr(along, "_halt", threading.Event())
    monkeypatch.setattr(along, "_modules_on", lambda: True)
    monkeypatch.setattr(along, "_live_holds_screen", lambda: False)
    monkeypatch.setattr(along, "_tarot_now", lambda _: False)
    monkeypatch.setattr(along, "_wait", lambda _: True)
    monkeypatch.setattr(hearing, "ear", SimpleNamespace(set_quiet=lambda _: None))
    monkeypatch.setattr(sense, "collect", lambda **kwargs: found)
    monkeypatch.setattr(sight_service, "interval", lambda: 100)
    def prepared(offer, _trace):
        offer.spoken = "新台词"
        offer.mood = "平静"
        return offer
    monkeypatch.setattr(along, "_prepare_direct", prepared)
    along._loop()
    return state


def test_latest_subtitle_replaces_only_an_unfinished_direct_generation(monkeypatch):
    state = _run_direct_loop(monkeypatch)
    assert state.epoch == 1
    assert "新的一句字幕" in state.pending
    assert state.offer.direct
    assert state.playback == "queued"


def test_new_subtitle_does_not_cut_off_a_generated_playback(monkeypatch):
    state = _run_direct_loop(monkeypatch, generated="旧字幕对应的台词")
    assert state.epoch == 0
    assert state.pending == "旧字幕"
    assert state.generated == "旧字幕对应的台词"
    assert "新的一句字幕" in state.held.summary


def test_stale_generation_callbacks_cannot_clear_the_new_candidate(monkeypatch):
    from app.modules.glance import along
    from app.modules.glance.situation import Offer, Situation
    from app.modules.glance.watch import Candidate, WatchSession

    now = time.time()
    offer = Offer("video", "video:clip", "new", now, 1, "新字幕", direct=True)
    state = along._State(on=True, character_id=1, pending="新字幕", offer=offer, trace_id="new-trace")
    situation = Situation()
    watch = WatchSession(situation)
    candidate = Candidate(1, "新字幕", "new", "video:clip", "new", now)
    watch.candidate = candidate
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "situation", situation)
    monkeypatch.setattr(along, "live", watch)

    assert not along.generated("旧台词", expected_trace="old-trace")
    along.finish_speak(False, expected_trace="old-trace")
    assert state.pending == "新字幕"
    assert state.offer is offer
    assert state.generated == ""
    assert watch.candidate is candidate
    assert watch.silent_notes == 0


def test_minicpm_generator_uses_the_eye_text_endpoint(monkeypatch):
    from app.modules.glance import service
    from app.modules.glance.direct import generator

    calls = []

    def react(prompt, timeout):
        calls.append((prompt, timeout))
        return {"ok": True, "text": "这个反转还挺突然"}

    monkeypatch.setenv("XIAOKE_ALONG_DIRECT_GENERATOR", "minicpm")
    monkeypatch.setattr(service, "eyes_react", react)
    assert generator() == "minicpm"
    result = asyncio.run(direct_reply({}, [
        {"role": "system", "content": "测试人设"},
        {"role": "user", "content": "刚刚片子里说：船要开了"},
    ], evidence="船要开了"))
    assert result["action"] == "speak"
    assert result["generator"] == "minicpm"
    assert len(calls) == 1
    assert "测试人设" in calls[0][0]
    assert "刚刚片子里说" in calls[0][0]
    assert calls[0][1] == 30


def test_minicpm_failure_does_not_fall_back_to_a_second_model(monkeypatch):
    from app.modules.glance import service

    monkeypatch.setenv("XIAOKE_ALONG_DIRECT_GENERATOR", "minicpm")
    monkeypatch.setattr(service, "eyes_react", lambda *_: {"ok": False, "text": "", "message": "busy"})
    result = asyncio.run(direct_reply({}, [], evidence="船要开了"))
    assert result["action"] == "protocol"
    assert not result["text"]
    assert result["attempts"][0]["errors"] == ["minicpm_error"]


def test_static_and_repeated_visuals_stay_silent_without_calling_a_model():
    from app.modules.glance import along
    from app.modules.glance.situation import Offer

    now = time.time()
    assert along._empty_offer(Offer("video", "video:clip", "a", now, 1, "画面手没动", direct=True))
    assert along._empty_offer(Offer("video", "video:clip", "b", now, 1, "标题：抖音\n光柱持续出现", direct=True))
    assert not along._empty_offer(Offer("video", "video:clip", "c", now, 1, "字幕：虽然这个温暖可能很短暂", direct=True))
    along._state.trail = ["画面：阿姨给小女孩涂东西"]
    along._state.last = "画面：阿姨给小女孩涂东西"
    assert along._empty_offer(Offer("video", "video:clip", "d", now, 1, "画面：阿姨给小女孩涂东西", direct=True))
    along._state.trail = []
    along._state.last = ""


def test_companion_filler_is_not_valid_interaction():
    from app.modules.glance.direct import evaluate

    assert evaluate("我不吵你，就挨着你等下一帧", evidence="画面手没动")["action"] == "hollow"
    assert evaluate("还是这个画面，我不重复说了", evidence="画面手没动")["action"] == "hollow"
    result = evaluate("他怎么一直不开门，我都替他着急了", evidence="手扶门把手")
    assert result["action"] == "speak"
    assert result["mood"] == "紧张"


def test_natural_instruction_requires_progress_not_narration():
    from app.modules.glance.direct import instruction

    prompt = instruction()
    assert "不是画面解说员" in prompt
    assert "接着刚才的话题往前走" in prompt
    assert "没有新理解" in prompt


def test_generator_reads_saved_vision_choice_and_environment_override(monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine
    from app.modules.glance.direct import generator
    from app.services import settings_store

    monkeypatch.delenv("XIAOKE_ALONG_DIRECT_GENERATOR", raising=False)
    database = create_engine("sqlite://")
    SQLModel.metadata.create_all(database)
    monkeypatch.setattr("app.db.engine", database)
    with Session(database) as session:
        settings_store.update(session, {"vision": {"generator": "minicpm"}})
    assert generator() == "minicpm"
    with Session(database) as session:
        settings_store.update(session, {"vision": {"generator": "chat"}})
    assert generator() == "chat"
    with Session(database) as session:
        settings_store.update(session, {"vision": {"generator": "minicpm"}})
    monkeypatch.setenv("XIAOKE_ALONG_DIRECT_GENERATOR", "chat")
    assert generator() == "chat"
