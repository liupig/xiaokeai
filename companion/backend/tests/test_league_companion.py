from app.modules.sight.league_companion import strategy


def test_kill_and_death_have_positive_but_distinct_response_directions():
    kill = strategy({}, ['你击杀了安妮'])
    death = strategy({}, ['你被安妮击杀'])
    assert '积极给情绪价值' in kill
    assert '主动给一句有温度的宽慰' in death
    assert '不能只把帅换成厉害' in kill
    assert '优先留白' not in death


def test_consecutive_deaths_get_sensitive_variation_not_blame():
    state = {'player_key': 'me', 'events': [
        {'EventName': 'ChampionKill', 'KillerName': 'other', 'VictimName': 'me'}
        for _ in range(2)]}
    assert '换一个宽慰角度' in strategy(state, ['你被安妮击杀'])
