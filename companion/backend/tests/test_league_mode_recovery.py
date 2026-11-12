import threading
from types import SimpleNamespace

import pytest

from app.modules.glance import along, league_mode, trace
from app.modules.glance.situation import Offer, Situation
from app.modules.glance.watch import WatchSession
from app.modules.sight import league_client


@pytest.fixture
def session(monkeypatch):
    clock = [100.0]
    state = along._State(on=True, character_id=1, spoke_at=100)
    sit = Situation()
    monkeypatch.setattr(along, '_state', state)
    monkeypatch.setattr(along, '_halt', threading.Event())
    monkeypatch.setattr(along, 'situation', sit)
    monkeypatch.setattr(along, 'live', WatchSession(sit))
    monkeypatch.setattr(along, 'time', SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(league_mode, 'time', SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(league_mode, 'mode', lambda: 'api')
    monkeypatch.setattr(league_client, 'start_polling', lambda: None)
    monkeypatch.setattr(trace, 'note_look', lambda *a, **k: 'trace')
    monkeypatch.setattr(trace, 'mark', lambda *a, **k: None)
    sample = dict(hero='乐芙兰', game_time=100, observed_at=100,
                  player_key='me', team='ORDER', events=[])
    monkeypatch.setattr(league_client, 'snapshot', lambda: dict(sample, observed_at=clock[0]))
    offers = []
    monkeypatch.setattr(along, '_prepare_direct', lambda offer, _: offer)
    monkeypatch.setattr(along, '_enqueue', lambda offer, _: offers.append(offer))
    return state, sit, sample, clock, offers


def test_api_mode_can_talk_without_kill_events(session, monkeypatch):
    state, sit, sample, clock, offers = session
    sit.talk = 'more'
    def advance(_):
        clock[0] += 36
        sample['game_time'] += 36
        return len(offers) >= 2
    monkeypatch.setattr(along, '_wait', advance)
    league_mode.run()
    assert offers[1].kind == 'company'
    assert '乐芙兰' in offers[1].summary
    assert '不代表没有交战' in offers[1].summary


def test_api_mode_keeps_recent_events_while_busy(session, monkeypatch):
    state, sit, sample, clock, offers = session
    waits = []
    def advance(_):
        waits.append(1)
        clock[0] += 1
        sample['game_time'] += 1
        if len(waits) == 1:
            state.speaking = True
            sample['events'] = [dict(EventID=1, EventTime=101, EventName='ChampionKill',
                                     KillerName='me', VictimName='other')]
        else:
            state.speaking = False
        return len(waits) >= 3
    monkeypatch.setattr(along, '_wait', advance)
    league_mode.run()
    assert len(offers) == 2
    assert offers[1].event_ids == [1]


def test_api_mode_releases_expired_queue(session, monkeypatch):
    state, sit, sample, clock, offers = session
    state.offer = Offer('game', 'league', 'old', 80, 1, '旧事件', max_age=8)
    state.pending = '旧事件'
    monkeypatch.setattr(along, '_wait', lambda _: True)
    league_mode.run()
    assert not state.pending
    assert offers


def test_source_switch_dispatches_to_visual_loop(session, monkeypatch):
    selected = ['api']
    calls = []
    monkeypatch.setattr(league_mode, 'mode', lambda: selected[0])
    def api_loop():
        calls.append('api')
        selected[0] = 'hybrid'
    monkeypatch.setattr(league_mode, 'run', api_loop)
    monkeypatch.setattr(along, '_loop', lambda: calls.append('hybrid'))
    along._run_loop()
    assert calls == ['api', 'hybrid']


def test_api_mode_respects_explicit_quiet(session, monkeypatch):
    state, sit, sample, clock, offers = session
    sit.talk = 'quiet'
    state.speak_locked = True
    clock[0] += 300
    monkeypatch.setattr(along, '_wait', lambda _: True)
    league_mode.run()
    assert offers == []


@pytest.mark.parametrize('text', ['你多多说话呀', '怎么都不说话？', '你都不说话'])
def test_silence_complaints_restore_talking(session, text):
    state, sit, *_ = session
    sit.talk = 'quiet'
    along.live.speak_locked = True
    along.live.user_says(text)
    assert sit.talk == 'more'
    assert not along.live.speak_locked
