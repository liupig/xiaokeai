from app.modules.sight.league_client import parse_state, roster_brief


def test_roster_is_relative_to_player_team_and_replaced_next_game():
    data = {'activePlayer': {'summonerName': 'me'}, 'allPlayers': [
        {'summonerName': 'other', 'championName': 'Annie', 'team': 'ORDER'},
        {'summonerName': 'me', 'championName': 'Caitlyn', 'team': 'CHAOS'},
        {'summonerName': 'ally', 'championName': 'Lux', 'team': 'CHAOS'}]}
    state = parse_state(data)
    text = roster_brief(state)
    assert '我方阵容：Caitlyn、Lux' in text
    assert '敌方阵容：Annie' in text
    data['allPlayers'][1]['championName'] = 'Garen'
    assert 'Caitlyn' not in roster_brief(parse_state(data))
    assert roster_brief({}) == ''
