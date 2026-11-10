from app.modules.glance.companion_intent import CompanionIntent


def test_goal_survives_reactions_and_listening_overrides_coaching():
    item = CompanionIntent()
    item.user('这把想练乐芙兰')
    item.user('别分析了，我就想吐槽')
    assert '乐芙兰' in item.context()
    assert '不自动给攻略' in item.context()
    item.user('帮我分析怎么打')
    assert '一个可选建议' in item.context()


def test_quiet_does_not_expire_and_session_reset_removes_goals():
    item = CompanionIntent()
    item.user('今天想练英雄，安静点')
    item.updated -= 900
    assert '不主动发言' in item.context()
    item.user('可以说话了')
    assert '问题一次一个' in item.context()
    item.reset()
    assert '用户目标原话' not in item.context()
