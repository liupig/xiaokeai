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
    attempted_at = 0.0
    match_object = 'league'
    waiting = False
    while not along._halt.is_set():
        if mode() != 'api' or not along._state.on:
            return
        state = snapshot()
        now = time.time()
        # An expired queue or a lost playback acknowledgement cannot block
        # the API source for the rest of the match.
        with along._lock:
            queued = along._state.offer
            expired = bool(queued and (
                (not along._state.speaking and not along._sayable(queued))
                or (along._state.speaking and now - along._state.speak_since >= 95)))
        if expired:
            along.finish_speak(False)
        if not state or now - state.get('observed_at', 0) > 5:
            if not waiting:
                from ... import talk_log
                talk_log.write('note', '英雄联盟对局API暂不可用，等待新鲜对局数据；不能据旧台词判断英雄或胜负')
            waiting = True
            along.situation.watch_feedback = '等待英雄联盟对局API；当前没有新鲜数据'
            if along._wait(1):
                return
            continue
        waiting = False
        fusion = fuse(state, previous, 0, now)
        summary = '；'.join(fusion['events'])
        same_match = bool(previous and previous.get('player_key') == state.get('player_key')
                          and previous.get('hero') == state.get('hero')
                          and previous.get('team') == state.get('team')
                          and state['game_time'] >= previous['game_time'])
        if not same_match:
            match_object = f"league:{state['hero']}:{int(now)}"
            summary = f"当前对局英雄：{state['hero']}；对局已进行{int(state['game_time'])}秒"
        rules = score_brief(state, previous) + '\n' + company('英雄联盟', '局内', summary)
        from ..sight.league_companion import strategy
        rules += '\n' + strategy(state, fusion['events'])
        with along._lock:
            busy = (along._state.pending or along._state.speaking or along._state.speak_locked
                    or now < along._state.user_until)
            last_spoke = along._state.spoke_at
        if busy:
            if along._wait(1):
                return
            continue
        # Keep the prior sample while busy so recent API events are not lost.
        previous = state
        company_due = (not summary and along.situation.talk != 'quiet'
                       and now - max(last_spoke, attempted_at) >=
                       (35 if along.situation.talk == 'more' else 75))
        if company_due:
            summary = (f"当前API确认玩家英雄：{state['hero']}；对局已进行{int(state['game_time'])}秒。"
                       "暂未收到新的玩家击杀事件，不代表没有交战。接一个与本局英雄有关的简短话题，"
                       "不要编操作、空档或重复追问；没自然的话可留白。")
        if summary and not busy:
            attempted_at = now
            from .trace import note_look, mark
            trace_id = note_look(dict(ok=True, channel='liveclient', text=summary,
                                      observed_at=now), {})
            mark(trace_id, league_snapshot=state, league_fusion=fusion,
                 source_process='League of Legends.exe', source_title='League of Legends',
                 handoff=summary)
            along.situation.scene = 'game'
            along.situation.object_id = match_object
            along.live.source_valid = True
            offer = Offer('game', match_object, 'api:' + str(state['game_time']), now, 1, summary,
                          channel='liveclient', speech_rule=rules + '\n纯API模式，不能描述走位、技能命中或画面。',
                          max_age=8, phase='lane', player_hero=state['hero'], direct=True,
                          event_ids=fusion['event_ids'])
            if not same_match:
                offer.max_age = 30
            if company_due:
                offer.kind = 'company'
                offer.max_age = 30
            offer = along._prepare_direct(offer, trace_id)
            if offer and along._sayable(offer):
                with along._lock:
                    along._enqueue(offer, trace_id)
        if along._wait(1):
            return
