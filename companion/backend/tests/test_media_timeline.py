import time
from types import SimpleNamespace

from app.modules.glance.media_timeline import MediaTimeline, Moment
from app.modules.glance.media_subtitles import SubtitleSampler
from app.modules.glance.hearing import Ear


def test_visual_subtitles_and_audio_keep_their_own_capture_times():
    stream = MediaTimeline()
    epoch = stream.bind("clip")
    stream.add(Moment(90, 90, visual="僧人抬手", subtitle="我不是师傅吗"), epoch=epoch, now=100)
    stream.add(Moment(91, 94, audio="你倒是听师傅的话呀"), epoch=epoch, now=100)
    stream.add(Moment(96, 96, visual="另一人指向木盒", transition="抬手后递出木盒"), epoch=epoch, now=100)
    text = stream.context(100)
    assert text.index("我不是师傅吗") < text.index("你倒是听师傅的话呀") < text.index("另一人指向木盒")
    assert "字幕原文" in text and "音频转写" in text and "片段长3.0秒" in text
    assert stream.rows(100)[0]["end"] == 90


def test_repeat_polling_does_not_rejuvenate_a_caption():
    stream = MediaTimeline()
    epoch = stream.bind("clip")
    stream.add(Moment(90, 90, subtitle="同一句字幕"), epoch=epoch, now=100)
    stream.add(Moment(100, 100, subtitle="同一句字幕"), epoch=epoch, now=100)
    assert len(stream.rows(100)) == 1
    assert stream.rows(100)[0]["end"] == 90
    assert not stream.rows(115)


def test_source_switch_seek_and_expiry_reject_old_results():
    stream = MediaTimeline()
    old = stream.bind("old")
    new = stream.bind("new")
    stream.add(Moment(99, 99, subtitle="旧视频台词"), epoch=old, now=100)
    assert not stream.rows(100)
    stream.cut(100)
    assert not stream.current(new, 99)
    assert stream.current(new, 101)
    stream.add(Moment(98, 101, audio="横跨跳转的声音"), epoch=new, now=102)
    stream.add(Moment(99, 99, subtitle="跳转前迟到的OCR"), epoch=new, now=102)
    stream.add(Moment(101, 101, subtitle="新字幕"), epoch=new, now=102)
    assert len(stream.rows(102)) == 1
    assert "新字幕" in stream.context(102)
    assert not stream.rows(126)


def test_bounded_context_keeps_picture_amid_many_subtitles():
    stream = MediaTimeline(capacity=16)
    epoch = stream.bind("clip")
    stream.add(Moment(90, 90, visual="画面事实" * 30), epoch=epoch, now=100)
    for i in range(10):
        stream.add(Moment(91+i, 91+i, subtitle=f"字幕{i}" * 25), epoch=epoch, now=100)
    stream.add(Moment(97, 100, audio="声音原文" * 30), epoch=epoch, now=100)
    text = stream.context(100)
    assert len(text) <= 1600
    assert "画面事实" in text and "声音原文" in text and "字幕9" in text


def test_subtitle_sampler_is_bounded_and_rejects_a_late_window_result():
    sampler = SubtitleSampler()
    sampler._thread = SimpleNamespace(is_alive=lambda: True)
    sampler.configure("old", lambda: {"ok": True, "text": "字幕：原来的视频"})
    for _ in range(12):
        sampler.sample()
    assert len(sampler.drain("old")) == 8

    def late():
        sampler.configure("new", lambda: {"ok": True, "text": "字幕：新视频"})
        return {"ok": True, "text": "字幕：旧窗口迟到"}

    sampler.configure("old", late)
    sampler.sample()
    assert sampler.drain("new") == []
    sampler.sample()
    assert sampler.drain("new")[0]["text"] == "字幕：新视频"
    sampler.reset()
    sampler.sample()
    assert sampler.drain("new") == []


def test_audio_recording_does_not_wait_for_asr_and_keeps_queue_bounded(monkeypatch):
    from app.modules.glance import hearing
    ear = Ear()
    captured = []

    def record(stop, seconds):
        captured.append(seconds)
        if len(captured) == 3:
            stop.set()
        return b"wav"

    monkeypatch.setattr(hearing, "_record_span", record)
    ear._run()
    assert captured == [3.2, 3.2, 3.2]
    assert ear._pending.qsize() == 2
    assert ear.diagnostics()["dropped"] == 1


def test_audio_transcript_uses_recording_time_not_asr_completion(monkeypatch):
    from app.services import asr
    ear = Ear()
    ear.bind("clip")
    now = time.time()
    monkeypatch.setattr(asr, "transcribe", lambda wav: "我不是师傅吗")
    assert ear._decode(b"wav", now-6, now-3, ear._generation)
    segment = ear.segment("我不是师傅吗")
    assert segment["start"] == now-6 and segment["end"] == now-3
    assert ear._at == now-3
    ear.bind("another")
    assert not ear.segments()
    assert not ear._decode(b"wav", now-6, now-3, ear._generation-1)


def test_silence_is_not_sent_to_asr():
    import numpy as np
    from app.modules.glance.hearing import _wav
    assert _wav(np.zeros((1600, 2), dtype=np.float32)) is None
    assert _wav(np.full((1600, 2), .1, dtype=np.float32))


def test_ocr_only_endpoint_never_runs_a_visual_model(monkeypatch):
    from app.modules.glance import service, vision, trace
    calls = []

    class Client:
        def post(self, url, **kwargs):
            calls.append((url, kwargs["json"]))
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                "ok": True, "ocr_text": "字幕：我不是师傅吗", "images": ["pixels"], "observed_at": 100,
            })

    monkeypatch.setattr(service, "_borrow", lambda: Client())
    monkeypatch.setattr(service, "_release", lambda _: None)
    monkeypatch.setattr(vision, "uses_local", lambda: True)
    monkeypatch.setattr(vision, "describe", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not invoke VLM")))
    notes = []
    monkeypatch.setattr(trace, "note_look", lambda data, pack, **kwargs: notes.append(pack) or "trace")
    found = service.eyes_glance(prompt="陪看视频", ocr_only=True, frames=1)
    assert calls[0][0].endswith("/api/frames")
    assert calls[0][1]["frames"] == 1
    assert found["text"] == "字幕：我不是师傅吗"
    assert "images" not in found
    assert not notes[0].get("captured") and not notes[0].get("sent")


def test_real_collect_merges_ocr_with_previous_visual_and_resets_on_seek(monkeypatch, tmp_path):
    from app.modules.glance import sense, along, media_session
    from app.modules.glance.media_timeline import timeline
    from app.modules.sight import service
    from app.modules.glance.desktop import Desk
    from app.modules.glance.media_director import bind_context
    from app.modules.glance.situation import Situation, parse_observation

    monkeypatch.setenv("SIGHT_HOME", str(tmp_path))
    service.reload()
    service.reset()
    sense.reset()
    now = time.time()
    desk = Desk(ok=True, hwnd=100, process="chrome.exe", app="抖音", title="抖音", window="抖音", kind="video")
    source = f"{desk.hwnd}:{desk.process}:{desk.title}"
    service.commit(desk.process, desk.title, desk.window, "标题：西游短片\n画面：僧人坐在树林里")
    epoch = timeline.bind(source)
    timeline.add(Moment(now-5, now-5, visual="僧人坐在树林里"), epoch=epoch, now=now)
    monkeypatch.setattr(sense, "read_foreground", lambda: desk)
    monkeypatch.setattr(sense, "_stick", lambda d: d)
    monkeypatch.setattr(sense, "_heard", lambda *args: "")
    monkeypatch.setattr(sense.motion, "see", lambda hwnd: "same")
    monkeypatch.setattr(sense, "ear", SimpleNamespace(bind=lambda _: None, clear=lambda: None, segments=lambda: []))
    monkeypatch.setattr(along, "snapshot", lambda: {"on": False})
    monkeypatch.setattr(sense, "_trace", lambda *args, **kwargs: None)
    metadata = {"title": "西游短片", "status": "playing", "position": 10}
    monkeypatch.setattr(media_session, "latest", lambda d: metadata)
    calls = []

    def ocr(d, **kwargs):
        calls.append(kwargs)
        return {"ok": True, "text": "字幕：我不是师傅吗", "observed_at": now-1}

    monkeypatch.setattr(sense, "_look", ocr)
    result = sense.collect(force=False)
    assert calls[0]["ocr_only"]
    assert not result["used_eyes"]
    assert "僧人坐在树林里" in result["sight"]["timeline"]
    assert "我不是师傅吗" in result["sight"]["timeline"]
    offer = Situation().ingest(parse_observation(result["text"]))
    assert offer is not None
    bind_context(offer, result["sight"])
    assert "僧人坐在树林里" in offer.context
    assert "我不是师傅吗" in offer.summary

    # A backward seek with the same platform/window title must cut old context.
    metadata["position"] = 1
    monkeypatch.setattr(sense, "_last_ocr", 0)
    monkeypatch.setattr(sense, "_look", lambda *args, **kwargs: {
        "ok": True, "text": "字幕：新的台词", "observed_at": now,
    })
    result = sense.collect(force=False)
    assert result.get("continuity_gap")
    assert "僧人坐在树林里" not in result["sight"]["timeline"]
    assert "我不是师傅吗" not in result["sight"]["timeline"]
    assert "新的台词" in result["sight"]["timeline"]
    sense.reset()
    service.reset()


def test_static_playback_counter_is_not_a_seek():
    from app.modules.sight.catalog import find_sub
    from app.modules.sight.media import update
    sub = find_sub("movie", "player")
    _, facts = update(sub, "playing", {"播放位置": "20", "播放状态": "playing", "观测时刻": "0"},
                      {"播放位置": "20", "播放状态": "playing", "画面": "僧人抬手"})
    assert "跳转" not in facts


def test_clip_transition_is_not_folded_into_the_current_picture():
    from app.modules.glance.situation import parse_observation
    obs = parse_observation("类型：video\n画面：人物现在坐下了\n经过：先前站着，然后坐下\n原文：我不是师傅吗")
    assert obs.visible_events == ["人物现在坐下了"]
    assert obs.visible_text == ["我不是师傅吗"]


def test_quiet_watch_still_listens_to_the_video(monkeypatch):
    from app.modules.glance import league_mode
    monkeypatch.setattr(league_mode, "mode", lambda: "hybrid")
    from app.modules.glance import along, hearing
    quiet = []
    monkeypatch.setattr(along, "_state", along._State(on=True, speak_locked=True))
    monkeypatch.setattr(along, "live", SimpleNamespace(eyes_on=False))
    monkeypatch.setattr(along, "_modules_on", lambda: True)
    monkeypatch.setattr(along, "_live_holds_screen", lambda: False)
    monkeypatch.setattr(along, "_tarot_now", lambda _: False)
    monkeypatch.setattr(along, "_wait", lambda _: True)
    monkeypatch.setattr(hearing, "ear", SimpleNamespace(set_quiet=quiet.append))
    along._loop()
    assert quiet == [False]


def test_video_identity_from_address_bar_cuts_same_platform_title():
    from app.modules.sight.media_ocr import facts
    from app.modules.sight.media import update
    from app.modules.sight.catalog import find_sub
    lines = [{"text": "douyin.com/jingxuan?modal_id=7691929558521531689",
              "words": [{"x": 140, "y": 53, "width": 370}]}]
    assert "媒体标识：douyin.com:7691929558521531689" in facts(lines, (1920, 1041), "video")
    sub = find_sub("video", "douyin")
    _, old = update(sub, "playing", {}, {"标题": "抖音", "媒体标识": "douyin.com:111111", "原文": "旧台词"})
    _, fresh = update(sub, "playing", old, {"标题": "抖音", "媒体标识": "douyin.com:222222", "原文": "新台词"})
    assert fresh["内容切换"] == "是"
    assert fresh["原文"] == "新台词"
    assert "旧台词" not in str(fresh)
    lines[0]["words"][0]["y"] = 800
    assert "媒体标识" not in facts(lines, (1920, 1041), "video")
