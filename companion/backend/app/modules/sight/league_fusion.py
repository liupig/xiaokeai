"""Merge timestamped API facts with visual observations without inventing causality."""
from __future__ import annotations


def fuse(state: dict, previous: dict, visual_at: float, now: float) -> dict:
    clock = float(state.get('game_time') or 0)
    stamp = float(state.get('observed_at') or 0)
    age = max(0, now - stamp)
    aligned = bool(stamp and visual_at and abs(stamp - visual_at) <= 3 and age <= 5)
    same = bool(previous and state.get('player_key') == previous.get('player_key')
                and state.get('hero') == previous.get('hero')
                and state.get('team') == previous.get('team')
                and clock >= float(previous.get('game_time') or 0))
    seen = {e.get('EventID') for e in previous.get('events', [])} if same else set()
    roster = {key: p.get('hero') or '未确认英雄' for p in state.get('roster', [])
              for key in p.get('keys', []) if key}
    own = state.get('player_key')
    moments = []
    fresh_ids = []
    for event in state.get('events', []):
        ident = event.get('EventID')
        if ident is None or ident in seen:
            continue
        seen.add(ident)
        elapsed = clock - float(event.get('EventTime') or 0)
        if age > 5 or not 0 <= elapsed <= 8:
            continue
        if event.get('EventName') != 'ChampionKill':
            continue
        killer, victim = event.get('KillerName'), event.get('VictimName')
        helpers = event.get('Assisters') or []
        if own == killer:
            line = '你击杀了' + roster.get(victim, '未确认身份的对手')
        elif own == victim:
            line = '你被' + roster.get(killer, '未确认身份的单位') + '击杀'
        elif own and own in helpers:
            line = '你参与助攻：' + roster.get(killer, '队友') + '击杀了' + roster.get(victim, '对手')
        else:
            continue
        moments.append(line)
        fresh_ids.append(ident)
    rules = ['API与视频时间接近，可以结合确认事实；接近不证明技能命中或因果。' if aligned else
             'API与视频没有可靠时间对齐。分别描述，不把画面动作归因于这些事件，不编技能命中、丝血或反杀。']
    if moments:
        rules.append('API新事件（每个事件只回应一次）：' + '；'.join(moments[-3:]))
    else:
        rules.append('没有新的玩家击杀事件，不复述累计战绩；首次连接不补播旧事件。')
    return dict(aligned=aligned, api_age=round(age, 3), event_ids=fresh_ids,
                events=moments, instruction='\n'.join(rules))
