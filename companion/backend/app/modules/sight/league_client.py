"""Optional read-only local LoL telemetry. No account credentials or game control."""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_checked = 0.0
_cached: dict = {}
_failures = 0
_next_probe = 0.0
_poll_stop = threading.Event()
_poll_thread = None


def start_polling() -> None:
    global _poll_thread, _poll_stop
    with _lock:
        if _poll_thread and _poll_thread.is_alive():
            return
        _poll_stop = threading.Event()
        token = _poll_stop
        def run():
            while not token.is_set():
                latest()
                token.wait(1)
        _poll_thread = threading.Thread(target=run, name='league-liveclient', daemon=True)
        _poll_thread.start()


def stop_polling() -> None:
    _poll_stop.set()
    thread = _poll_thread
    if thread and thread is not threading.current_thread():
        thread.join(timeout=1)


def snapshot() -> dict:
    with _lock:
        return dict(_cached)


def connection_status() -> dict:
    with _lock:
        return {'state': 'ready' if _cached else 'waiting', 'failures': _failures,
                'retry_in': round(max(0, _next_probe - time.monotonic()), 2)}

_LEAGUE_PROCESSES = {
    "leagueclient.exe",
    "leagueclientux.exe",
    "league of legends.exe",
    "leagueclientuxrender.exe",
}


def is_league_process(process: str) -> bool:
    """Accept client, UX and in-game process names (Windows reports all three)."""
    name = str(process or "").replace("\\", "/").rsplit("/", 1)[-1].lower().strip()
    return name in _LEAGUE_PROCESSES


def parse_state(data: dict) -> dict:
    active = data.get("activePlayer") or {}
    name = active.get("summonerName")
    riot_id = active.get("riotId")
    players = data.get("allPlayers") or []
    own = next((p for p in players if (name and p.get("summonerName") == name)
                or (riot_id and p.get("riotId") == riot_id)), None)
    if not own or not own.get("championName"):
        return {}
    return {
        "hero": str(own["championName"]),
        "dead": bool(own.get("isDead")),
        "respawn": float(own.get("respawnTimer") or 0),
        "game_time": float((data.get("gameData") or {}).get("gameTime") or 0),
        "scores": dict(own.get("scores") or {}),
        "source": "liveclient",
        "team": own.get("team", ""),
        "players": [{"team": p.get("team", ""), "scores": dict(p.get("scores") or {})} for p in players],
        "objectives": objective_counts(data, own.get('team', '')),
        "current_gold": active.get('currentGold'),
        "player_key": str(riot_id or name or ''),
        "roster": [{"hero": p.get('championName', ''), "team": p.get('team', ''),
                    "position": p.get('position', ''), "level": p.get('level'),
                    "dead": bool(p.get('isDead')), "scores": dict(p.get('scores') or {}),
                    "keys": [p.get('riotId'), p.get('summonerName')]} for p in players],
        "events": list((data.get('events') or {}).get('Events') or []),
        "observed_at": time.time(),
        "level": own.get('level'),
        "health": (active.get('championStats') or {}).get('currentHealth'),
        "max_health": (active.get('championStats') or {}).get('maxHealth'),
        "items": [dict(itemID=i.get('itemID'), name=i.get('displayName', ''), count=i.get('count', 1))
                  for i in own.get('items', [])],
    }


def roster_brief(state: dict) -> str:
    team = state.get('team')
    if team not in {'ORDER', 'CHAOS'} or not state.get('roster'):
        return ''
    def show(player):
        hero = str(player.get('hero') or '未知英雄')
        position = str(player.get('position') or '')
        # Position is a declared lane, never a world coordinate.
        return hero + (f'（分路标记：{position}）' if position else '')
    ours = [show(p) for p in state['roster'] if p.get('team') == team]
    theirs = [show(p) for p in state['roster'] if p.get('team') in {'ORDER', 'CHAOS'} and p.get('team') != team]
    return (f"当前API玩家英雄：{state.get('hero', '未知')}。\n我方阵容：" + '、'.join(ours) +
            '\n敌方阵容：' + '、'.join(theirs) +
            '\n这是本局名单，以本次名单覆盖历史阵容。可讨论开团、保护、消耗、前排和伤害构成的条件性取舍；'
            '角色定位属于分析，不是当前站位或已发生事件。不编队友实时位置、技能冷却、经济、胜率或必胜结论。'
            '用户提问才展开阵容讨论，日常不循环念名单；不确定英雄机制或版本时说明不确定。')


def objective_counts(data: dict, team: str) -> dict:
    """Attribute objectives by killer identity or destroyed structure team."""
    teams = {str(p.get(key)): p.get('team') for p in data.get('allPlayers', [])
             for key in ('summonerName', 'riotId') if p.get(key)}
    rows = (data.get('events') or {}).get('Events')
    if not isinstance(rows, list) or team not in {'ORDER', 'CHAOS'}:
        return {}
    counts = {kind: [0, 0] for kind in ('防御塔', '小龙', '大龙', '峡谷先锋', '水晶')}
    seen = set()
    for event in rows:
        ident = event.get('EventID')
        if ident is not None and ident in seen:
            continue
        if ident is not None:
            seen.add(ident)
        kind = {'TurretKilled': '防御塔', 'DragonKill': '小龙', 'BaronKill': '大龙',
                'HeraldKill': '峡谷先锋', 'InhibKilled': '水晶'}.get(event.get('EventName'))
        if not kind:
            continue
        killer_team = teams.get(str(event.get('KillerName') or ''))
        if kind in {'防御塔', '水晶'}:
            target = str(event.get('TurretKilled') or event.get('InhibKilled') or '')
            destroyed = 'ORDER' if '_T1_' in target else 'CHAOS' if '_T2_' in target else ''
            if destroyed:
                killer_team = 'CHAOS' if destroyed == 'ORDER' else 'ORDER'
        if killer_team in {'ORDER', 'CHAOS'}:
            counts[kind][0 if killer_team == team else 1] += 1
    return counts


def score_brief(state: dict, previous: dict | None = None) -> str:
    """Only measured counters; kill lead is not an economic or overall lead."""
    scores = state.get('scores') or {}
    fields = ('kills', 'deaths', 'assists', 'creepScore')
    if not all(isinstance(scores.get(k), (int, float)) for k in fields):
        return ''
    k, d, a, cs = (int(scores[f]) for f in fields)
    minutes = float(state.get('game_time') or 0) / 60
    lines = [roster_brief(state), f'玩家战绩：{k}/{d}/{a}（击杀/死亡/助攻）；补刀{cs}']
    if minutes >= 1:
        lines.append(f'补刀速率：{cs / minutes:.1f}/分钟；不根据此值评价辅助或打野表现')
    team = state.get('team')
    players = state.get('players') or []
    ours = [p for p in players if team and p.get('team') == team]
    theirs = [p for p in players if p.get('team') and p.get('team') != team]
    if ours and theirs and all(isinstance((p.get('scores') or {}).get('kills'), (int, float)) for p in ours + theirs):
        own_k = sum(int(p['scores']['kills']) for p in ours)
        enemy_k = sum(int(p['scores']['kills']) for p in theirs)
        delta = own_k - enemy_k
        trend = '击杀数领先' if delta > 0 else '击杀数落后' if delta < 0 else '击杀数持平'
        lines.append(f'团队击杀：{own_k}:{enemy_k}，{trend}；仅是击杀维度，不代表整体优势、经济或胜率')
    old = (previous or {}).get('scores') or {}
    same_match = bool(previous and previous.get('hero') == state.get('hero') and previous.get('team') == team
                      and float(previous.get('game_time') or 0) <= float(state.get('game_time') or 0)
                      and all(isinstance(old.get(f), (int, float)) and scores[f] >= old[f] for f in fields))
    if same_match:
        if state.get('level') and previous.get('level') and state['level'] > previous['level']:
            lines.append(f"等级变化：升至{state['level']}级；不据此编技能加点。")
        before_items = {i.get('itemID') for i in previous.get('items', [])}
        new_items = [i.get('name') for i in state.get('items', []) if i.get('itemID') not in before_items and i.get('name')]
        if new_items:
            lines.append('装备栏新增：' + '、'.join(new_items) + '；新增不等于购买，可能是合成或自动获得。')
        changes = [(label, int(scores[f] - old[f])) for f, label in zip(fields[:3], ('击杀', '死亡', '助攻')) if scores[f] > old[f]]
        if changes:
            lines.append('战绩变化：' + '、'.join(f'{label}+{n}' for label, n in changes))
        else:
            lines.append('战绩变化：无新增击杀、死亡或助攻，不重复点评旧战绩')
    objectives = state.get('objectives') or {}
    if objectives:
        lines.append('目标累计（我方:对方）：' + '；'.join(f'{name}{pair[0]}:{pair[1]}' for name, pair in objectives.items()))
        lines.append('水晶是累计摧毁次数，不代表当前仍被摧毁；大龙是累计击杀，不代表增益仍在。')
        if same_match:
            old_objectives = (previous or {}).get('objectives') or {}
            changes = []
            for name, pair in objectives.items():
                before = old_objectives.get(name)
                if before and all(pair[i] >= before[i] for i in (0, 1)):
                    changes.extend(f'{side}{name}+{pair[i]-before[i]}' for i, side in enumerate(('我方', '对方')) if pair[i] > before[i])
            lines.append('目标变化：' + ('、'.join(changes) if changes else '无新增，不重复播报累计目标'))
        tower = objectives.get('防御塔', [0, 0])
        dragon = objectives.get('小龙', [0, 0])
        lines.append('局势解读：分别讨论击杀差、推塔进度和小龙积累；指标相反时明确局势有取舍，不能合成为虚构经济差或胜率。')
    gold = state.get('current_gold')
    health, maximum = state.get('health'), state.get('max_health')
    if isinstance(health, (int, float)) and isinstance(maximum, (int, float)) and maximum > 0:
        lines.append(f'采样时生命值：{health:.0f}/{maximum:.0f}；不是当前精确值，不由此推断受谁攻击或技能命中。')
    if isinstance(gold, (int, float)):
        lines.append(f'玩家当前未花金币：{int(gold)}；不是累计总经济，不用于判断经济领先。')
    lines.append('局势限制：双方总经济不可用，不判断经济优势或胜率。个人战绩与团队局势分别讨论；死亡不责备，助攻也是贡献。')
    return '\n'.join(lines)


def latest() -> dict:
    """Bounded cached probe; unavailability must never block visual companionship."""
    global _checked, _cached, _failures, _next_probe
    with _lock:
        if time.monotonic() < _next_probe or time.monotonic() - _checked < 1:
            return dict(_cached)
        _checked = time.monotonic()
        try:
            import httpx

            # The game's localhost API uses its own certificate. Never send this
            # request to a configurable external URL, and never use proxy env vars.
            with httpx.Client(verify=False, trust_env=False, timeout=0.3) as client:
                response = client.get("https://127.0.0.1:2999/liveclientdata/allgamedata")
                response.raise_for_status()
                _cached = parse_state(response.json())
                if not _cached:
                    raise ValueError('active player not ready')
                _failures = 0
                _next_probe = time.monotonic() + 1
        except Exception:
            _cached = {}
            _failures = min(_failures + 1, 6)
            _next_probe = time.monotonic() + min(30, 2 ** _failures)
        return dict(_cached)
