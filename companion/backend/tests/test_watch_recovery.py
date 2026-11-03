"""Regression coverage for commentary expiry and silent worker failures."""
import threading

import pytest

from app.modules.glance import along
from app.modules.glance.situation import Offer, Situation
from app.modules.glance.watch import WatchSession


@pytest.fixture
def watching(monkeypatch):
    sit = Situation()
    state = along._State(on=True, character_id=1)
    monkeypatch.setattr(along, "situation", sit)
    monkeypatch.setattr(along, "live", WatchSession(sit))
    monkeypatch.setattr(along, "_state", state)
    monkeypatch.setattr(along, "_halt", threading.Event())
    monkeypatch.setattr(along.time, "time", lambda: 115.0)
    return state


def test_routine_generation_finishes_without_extending_queue_lifetime(watching):
    state = watching
    state.offer = Offer("game", "game:league", "topic", 100, 1, "英雄走到河道", phase="lane", max_age=12)
    assert not along.candidate_alive()
    state.speaking = True
    state.speak_since = 109
    assert along.candidate_alive()
    state.speak_since = 106
    assert not along.candidate_alive()
    state.speak_since = 109
    state.offer.observation_time = 94
    assert not along.candidate_alive()


@pytest.mark.parametrize("phase,age", [("fight", 8), ("dead", 6)])
def test_urgent_events_keep_strict_expiry(watching, phase, age):
    state = watching
    state.offer = Offer("game", "game:league", "topic", 100, 1, "局内事件", phase=phase, max_age=age)
    state.speaking = True
    state.speak_since = 110
    assert not along.candidate_alive()


def test_generation_grace_does_not_override_user_or_source(watching):
    state = watching
    state.offer = Offer("game", "game:league", "topic", 100, 1, "英雄走到河道", phase="lane", max_age=12)
    state.speaking = True
    state.speak_since = 109
    state.user_until = 120
    assert not along.candidate_alive()
    state.user_until = 0
    along.live.source_valid = False
    assert not along.candidate_alive()


def test_worker_retries_after_capture_exception(watching, monkeypatch):
    calls, logs = [], []

    def collect_loop():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("capture failed")

    monkeypatch.setattr(along, "_loop", collect_loop)
    monkeypatch.setattr(along, "_wait", lambda _: False)
    from app import talk_log
    monkeypatch.setattr(talk_log, "write", lambda *args, **kwargs: logs.append(args))
    along._run_loop()
    assert len(calls) == 2
    assert "capture failed" in logs[0][1]


def test_unknown_module_state_retries_without_stopping(watching, monkeypatch):
    monkeypatch.setattr(along, "_modules_on", lambda: None)
    waits = []
    monkeypatch.setattr(along, "_wait", lambda seconds: waits.append(seconds) or True)
    along._loop()
    assert watching.on
    assert waits == [2]
