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


def test_visual_off_uses_cached_status_without_health_check(monkeypatch):
    from app.modules.glance import along, eyes_host
    from app.modules.sight import league_client

    monkeypatch.setattr(league_client, 'snapshot', lambda: {})
    monkeypatch.setattr(along, 'snapshot', lambda: {'on': False})
    monkeypatch.setattr(eyes_host, 'cached_status', lambda: {'eyes': 'down', 'message': ''})
    monkeypatch.setattr(eyes_host, 'eyes_status', lambda: (_ for _ in ()).throw(
        AssertionError('visual-off chat must not probe the eyes service')))
    assert '视觉状态：down' in game_truth.context(20)


def test_visual_on_checks_live_status(monkeypatch):
    from app.modules.glance import along, eyes_host
    from app.modules.sight import league_client

    monkeypatch.setattr(league_client, 'snapshot', lambda: {})
    monkeypatch.setattr(along, 'snapshot', lambda: {'on': True})
    monkeypatch.setattr(eyes_host, 'eyes_status', lambda: {'eyes': 'up', 'message': ''})
    assert '视觉状态：up' in game_truth.context(20)
