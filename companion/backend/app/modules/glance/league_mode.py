"""Persisted LoL mode and a capture-free API observation source."""
import json
import time
from ...paths import DATA_DIR


def sync_visual_mode():
    """Resolve user permission plus runtime, not merely a configured remote URL."""
    from .eyes_host import eyes_status
    from sqlmodel import Session
    from ...db import engine
    from ...services import settings_store
    with Session(engine) as session:
        enabled = bool((settings_store.get_all(session).get('modules') or {}).get('glance'))
    phase = eyes_status().get('eyes') if enabled else 'down'
    selected = 'hybrid' if enabled and phase in {'up', 'starting', 'remote'} else 'api'
    set_mode(selected)
    return selected


def mode():
    try:
        value = json.loads((DATA_DIR / 'league-mode.json').read_text(encoding='utf-8')).get('mode')
        return value if value in ('api', 'hybrid') else 'api'
    except (OSError, ValueError):
        return 'api'


def set_mode(value):
    if value not in ('api', 'hybrid'):
        raise ValueError('mode must be api or hybrid')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'league-mode.json').write_text(json.dumps({'mode': value}), encoding='utf-8')


def run():
    from . import along
    from .situation import Offer
    from ..sight.league_client import start_polling, snapshot, score_brief
    from ..sight.league_fusion import fuse
    from ..sight.game_company import company
    start_polling()
    previous = {}
    while not along._halt.is_set():
        state = snapshot()
        now = time.time()
        if not state or now - state.get('observed_at', 0) > 5:
            if along._wait(1):
                return
            continue
        fusion = fuse(state, previous, 0, now)
        summary = '；'.join(fusion['events'])
        if not previous:
            summary = f"当前对局英雄：{state['hero']}；对局已进行{int(state['game_time'])}秒"
        rules = score_brief(state, previous) + '\n' + company('英雄联盟', '局内', summary)
        from ..sight.league_companion import strategy
        rules += '\n' + strategy(state, fusion['events'])
        previous = state
        with along._lock:
            busy = (along._state.pending or along._state.speaking or along._state.speak_locked
                    or now < along._state.user_until)
        if summary and not busy:
            from .trace import note_look, mark
            trace_id = note_look(dict(ok=True, channel='liveclient', text=summary,
                                      observed_at=now), {})
            mark(trace_id, league_snapshot=state, league_fusion=fusion,
                 source_process='League of Legends.exe', source_title='League of Legends',
                 handoff=summary)
            along.situation.scene = 'game'
            along.situation.object_id = 'league'
            along.live.source_valid = True
            offer = Offer('game', 'league', 'api:' + str(state['game_time']), now, 1, summary,
                          channel='liveclient', speech_rule=rules + '\n纯API模式，不能描述走位、技能命中或画面。',
                          max_age=8, phase='lane', player_hero=state['hero'], direct=True,
                          event_ids=fusion['event_ids'])
            offer = along._prepare_direct(offer, trace_id)
            if offer and along._sayable(offer):
                with along._lock:
                    along._enqueue(offer, trace_id)
        if along._wait(1):
            return
