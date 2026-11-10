from app.modules.sight.league_fusion import fuse


def state(clock=100):
    return dict(player_key='me', hero='LeBlanc', team='ORDER', game_time=clock, observed_at=1000,
                roster=[dict(hero='Annie', keys=['enemy'])],
                events=[dict(EventID=1, EventTime=99, EventName='ChampionKill',
                             KillerName='me', VictimName='enemy', Assisters=[])])


def test_kill_identity_alignment_and_duplicate_delivery():
    sample = state()
    first = fuse(sample, {}, 999, 1000)
    assert first['aligned'] and first['events'] == ['你击杀了Annie']
    assert fuse(sample, sample, 999, 1000)['events'] == []


def test_death_and_assist_are_not_personal_kills():
    sample = state()
    sample['events'][0].update(KillerName='enemy', VictimName='me')
    assert fuse(sample, {}, 999, 1000)['events'] == ['你被Annie击杀']
    sample['events'][0].update(VictimName='other', Assisters=['me'])
    assert '参与助攻' in fuse(sample, {}, 999, 1000)['events'][0]


def test_stale_video_or_api_does_not_invent_causality():
    assert not fuse(state(), {}, 980, 1000)['aligned']
    assert fuse(state(), {}, 999, 1010)['events'] == []
    assert fuse(state(clock=200), {}, 999, 1000)['events'] == []


def test_new_match_reuses_event_ids_without_losing_new_event():
    assert fuse(state(), state(clock=900), 999, 1000)['event_ids'] == [1]
