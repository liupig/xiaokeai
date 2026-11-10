from app.modules.glance import game_truth


def test_user_correction_overrides_old_hero_and_is_character_scoped(monkeypatch):
    from app.modules.sight import league_client
    monkeypatch.setattr(league_client, 'snapshot', lambda: {})
    monkeypatch.setattr(game_truth, '_corrections', {})
    game_truth.note(20, '我玩的女警')
    assert '本局玩的英雄是女警' in game_truth.context(20)
    assert '女警' not in game_truth.context(21)
    assert '历史助手发言不是游戏证据' in game_truth.context(20)


def test_correction_expires(monkeypatch):
    from app.modules.sight import league_client
    monkeypatch.setattr(league_client, 'snapshot', lambda: {})
    monkeypatch.setattr(game_truth, '_corrections', {20: ('女警', 1)})
    assert '本局玩的英雄是女警' not in game_truth.context(20)
