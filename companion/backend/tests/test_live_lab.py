"""虚构弹幕走正式主持，使用虚拟时钟完成整场回放；不冒充真实音频验收。"""
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.live.lab import LiveLab
from app.modules.live.lab_journal import LabJournal
from app.modules.live.lab_scenarios import SCENARIOS
from app.modules.live.events import LiveEvent


@pytest.fixture
def lab(tmp_path):
    instance = LiveLab(LabJournal(tmp_path / "live-lab.sqlite3"))
    yield instance
    instance.stop()


def finish(lab, start=1000, outcome="completed"):
    for now in range(start, start + 300):
        lab.step(now)
        turn = lab.host._turn
        if turn:
            assert lab.ack(turn["id"], outcome, now=now + .5)
        if lab.state == "completed":
            return lab.report()
    raise AssertionError(f"场景没有结束：{lab.state}，剩余 {len(lab.host.queue)} 条")


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_complete_scenario_replay_has_receipts_and_no_unsettled_gifts(lab, scenario):
    lab.start(scenario, background=False, now=1000)
    report = finish(lab)
    assert report["summary"]["received"] == len(SCENARIOS[scenario]["cues"])
    assert report["summary"]["turns"] >= 2
    assert report["checks"]["unique_turn_ids"]
    assert report["checks"]["unique_ack_ids"]
    assert report["checks"]["no_unsettled_paid"]
    assert report["checks"]["source_completed"]
    assert report["virtual_clock"] is True
    assert all(row["data"]["simulation"] for row in report["trace"] if row["kind"] == "ack")


def test_followups_reach_real_prompt_history(lab):
    lab.start("followup", background=False, now=1000)
    report = finish(lab)
    turns = [r["data"] for r in report["trace"] if r["kind"] == "turn"]
    assert any("土豆" in r["text"] for r in turns)
    assert any("小雨" in r["text"] and "钓鱼" in r["text"] for r in turns)
    assert any("慢慢来农场" in r["text"] for r in turns)
    assert len(lab.host._dialogue) == 4


def test_restart_keeps_journal_and_exposes_unfinished_paid_events(lab):
    lab.start(background=False, now=1000)
    lab.inject("支持你", "礼物观众", "gift", "小心心", 3)
    run = lab.run_id
    lab.stop()
    restored = LiveLab(LabJournal(lab.journal.path))
    report = restored.report(run)
    assert report["summary"]["pending_paid"] == 1
    assert report["pending_paid"][0]["nickname"] == "礼物观众"
    assert restored.journal.history()[0]["run_id"] == run


def test_model_failure_falls_back_without_stalling(lab):
    lab.start(background=False, now=1000)
    lab.fault("model")
    report = finish(lab)
    assert report["summary"]["model_failures"] == 1
    assert lab.host.health.llm_failures == 1
    assert report["checks"]["source_completed"]


def test_failed_playback_is_not_counted_as_delivered_paid_event(lab):
    lab.start(background=False, now=1000)
    lab.inject("支持你", "礼物观众", "gift", "小心心", 3)
    lab.step(1001)
    assert lab.ack(lab.host._turn["id"], "failed", now=1002)
    report = lab.report()
    assert report["summary"]["outcomes"] == {"failed": 1}
    assert report["summary"]["pending_paid"] == 1
    assert report["checks"]["has_playback_evidence"] is False
    assert lab.host._dialogue == lab.host._dialogue.__class__(maxlen=4)


def test_duplicate_replay_does_not_repeat_board_or_turn(lab):
    lab.start(background=False, now=1000)
    lab.step(1001)
    size = len(lab.host._board)
    lab.fault("duplicate")
    assert len(lab.host._board) == size
    assert lab.host.intake.counts["duplicate"] == 1


def test_disconnect_recovers_and_stop_invalidates_pending_turn(lab, monkeypatch):
    lab.start(background=False, now=1000)
    monkeypatch.setattr("app.modules.live.lab.time.time", lambda: 1000)
    lab.fault("disconnect")
    lab.step(1003)
    assert lab.elapsed == 0
    lab.step(1006)
    lab.step(1007)
    assert lab.elapsed == 1
    report = lab.report()
    assert any(row["kind"] == "source_reconnected" for row in report["trace"])
    lab.stop()
    assert lab.host._turn is None
    assert not lab.host.on_air


def test_api_start_inject_ack_export_and_stop(lab, monkeypatch):
    from app.modules.live import lab_router
    monkeypatch.setattr(lab_router, "get_lab", lambda: lab)
    original = lab.start
    monkeypatch.setattr(lab, "start", lambda *a, **kw: original(*a, **kw, background=False, now=1000))
    app = FastAPI()
    app.include_router(lab_router.router)
    with TestClient(app) as client:
        start = client.post("/api/live-lab/start", json={"scenario": "mixed"})
        assert start.status_code == 200
        assert start.json()["state"] == "running"
        assert client.post("/api/live-lab/inject", json={"content": "你喜欢什么游戏？"}).status_code == 200
        lab.step(1004)
        lab.step(1007)
        state = client.get("/api/live-lab/state").json()
        turn = state["host"]["turn"]
        assert turn["sources"]
        receipt = client.post("/api/live-lab/ack", json={"turn_id": turn["id"], "outcome": "displayed"})
        assert receipt.json()["ok"]
        assert not client.post("/api/live-lab/ack", json={"turn_id": turn["id"], "outcome": "completed"}).json()["ok"]
        report = client.get("/api/live-lab/report")
        assert report.status_code == 200
        assert "attachment" in report.headers["content-disposition"]
        assert report.json()["summary"]["outcomes"] == {"displayed": 1}
        assert "api_key" not in json.dumps(report.json())
        assert client.post("/api/live-lab/stop").json()["state"] == "stopped"
        assert client.post("/api/live-lab/inject", json={"content": "停止后"}).status_code == 400


def test_recover_paid_after_restart_only_settles_original_when_played(lab):
    lab.start(background=False, now=1000)
    lab.inject("支持你", "礼物观众", "gift", "小心心", 3)
    run = lab.run_id
    lab.stop()
    recovered = LiveLab(LabJournal(lab.journal.path))
    recovered.recover_paid(run, background=False, now=1100)
    assert recovered.report(run)["summary"]["pending_paid"] == 1
    report = finish(recovered, start=1100)
    assert report["summary"]["pending_paid"] == 0
    assert recovered.report(run)["summary"]["pending_paid"] == 0
    with pytest.raises(ValueError, match="没有待补播"):
        recovered.recover_paid(run, background=False, now=1200)


def test_simulated_receipts_never_claim_real_audio_verification(lab):
    lab.start("followup", background=False, now=1000)
    report = finish(lab)
    assert report["summary"]["outcomes"]["completed"] > 0
    assert not report["checks"]["has_playback_evidence"]


def test_same_topic_does_not_trigger_repeated_replies_during_rolling_flood(lab):
    lab.start("quiet", background=False, now=1000)
    lab.step(1000)
    lab.step(1003)
    lab.ack(lab.host._turn["id"], "completed", now=1004)
    for i in range(4):
        lab._ingest(LiveEvent("rehearsal", "comment", f"新观众{i}", "嗨，有人在吗？",
                              uid=str(i), msg_id=f"rolling-{i}", ts=1005), 1005)
    assert len(lab.host.queue) == 0


def test_only_one_stage_can_claim_and_ack_a_turn(lab):
    lab.start("followup", background=False, now=1000)
    lab.step(1000)
    lab.step(1003)
    turn = lab.host._turn
    assert lab.claim(turn["id"], "stage-a")
    assert not lab.claim(turn["id"], "stage-b")
    assert not lab.ack(turn["id"], "completed", now=1004, player_id="stage-b")
    assert lab.host._turn is not None
    assert lab.ack(turn["id"], "completed", now=1004, player_id="stage-a")
    assert lab.host._turn is None
    assert len([r for r in lab.report()["trace"] if r["kind"] == "ack"]) == 1


def test_slow_generation_does_not_block_simulated_capture(lab, monkeypatch):
    import time
    from threading import Event
    from app.modules.live.lab_scenarios import Cue
    started, release = Event(), Event()
    monkeypatch.setitem(SCENARIOS, "short", {"name": "隔离验证", "duration": 2,
                        "cues": [Cue(0, "a", "第一句"), Cue(.5, "b", "第二句"), Cue(1, "c", "第三句")]})

    def slow(_conf, _messages):
        started.set()
        release.wait(4)
        return "接着聊。", 0

    monkeypatch.setattr("app.modules.live.lab.scripted_reply", slow)
    lab.start("short", background=True)
    lab.host.cfg()["pace"]["batch_size"] = 1
    try:
        assert started.wait(3)
        deadline = time.monotonic() + 2
        while lab._index < 3 and time.monotonic() < deadline:
            Event().wait(.05)
        assert lab._index == 3
        assert lab.host._generating
    finally:
        release.set()
        lab.stop()
