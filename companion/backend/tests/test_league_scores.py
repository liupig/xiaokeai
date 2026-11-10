from app.modules.sight.league_client import score_brief
from app.modules.sight.league_client import objective_counts


def test_objectives_use_structure_owner_and_deduplicate_events():
    tower = dict(EventID=1, EventName='TurretKilled', TurretKilled='Turret_T2_C_05_A', KillerName='Minion')
    data = dict(allPlayers=[dict(summonerName='enemy', team='CHAOS')], events=dict(Events=[
        tower, tower, dict(EventID=2, EventName='DragonKill', KillerName='enemy'),
        dict(EventID=3, EventName='BaronKill', KillerName='unknown')]))
    found = objective_counts(data, 'ORDER')
    assert found['防御塔'] == [1, 0]
    assert found['小龙'] == [0, 1]
    assert found['大龙'] == [0, 0]
    assert objective_counts({}, 'ORDER') == {}


def sample(k=1, d=2, a=8, clock=600):
    scores = dict(kills=k, deaths=d, assists=a, creepScore=50)
    return dict(hero='LeBlanc', team='ORDER', game_time=clock, scores=scores,
                players=[dict(team='ORDER', scores=scores),
                         dict(team='CHAOS', scores=dict(kills=10))])


def test_personal_success_does_not_imply_team_lead():
    text = score_brief(sample(k=8))
    assert '8/2/8' in text and '击杀数落后' in text
    assert '不代表整体优势' in text


def test_changes_and_unchanged_scores():
    assert '助攻+1' in score_brief(sample(a=9, clock=610), sample())
    assert '不重复点评' in score_brief(sample(clock=610), sample())


def test_new_game_does_not_report_negative_or_old_changes():
    assert '战绩变化' not in score_brief(sample(clock=1), sample(clock=900))
    assert score_brief(dict(scores={})) == ''
