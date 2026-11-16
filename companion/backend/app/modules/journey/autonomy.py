"""Character-owned preferences and slowly evolving inner continuity."""
from __future__ import annotations

import asyncio
import json

from ...models import Character
from ...services import llm, settings_store
from . import service
from .content import TAG_NAMES


_tasks = set()


def reflection_needed(character_id):
    with service._lock, service.connect() as db:
        now = service._now()
        service._ensure(db, character_id, now)
        row = db.execute('SELECT mode,ai_xp,self_note,autonomy_xp,autonomy_pending,autonomy_retry_at FROM journey_state WHERE character_id=?',
                         (character_id,)).fetchone()
        if row['mode'] != 'full' or row['autonomy_pending'] or row['autonomy_retry_at'] > now:
            return False
        return not row['self_note'] or row['ai_xp'] >= row['autonomy_xp'] + 120


def schedule_if_needed(session, character_id):
    if not reflection_needed(character_id):
        return False
    character = session.get(Character, character_id)
    if not character:
        return False
    conf = dict(settings_store.get_all(session).get('llm') or {})
    locale = settings_store.get_all(session).get('locale') or {}
    with service._lock, service.connect() as db:
        current = service._state(db, character_id, service._now())
        gift_count = db.execute('SELECT COUNT(*) AS n FROM journey_gifts WHERE character_id=?',
                                (character_id,)).fetchone()['n']
        db.execute('UPDATE journey_state SET autonomy_pending=1 WHERE character_id=?', (character_id,))
        db.commit()
    payload = {
        'character_id': character_id,
        'name': character.name,
        'persona': (character.persona or '')[:1800],
        'personality': (character.personality or '')[:700],
        'scenario': (character.scenario or '')[:500],
        'language': locale.get('reply') or 'zh-CN',
        'current_preferences': current['preferences'],
        'affection': current['affection'],
        'memory_count': current['memory_count'],
        'gift_count': gift_count,
        'revision': current['autonomy']['revision'] + 1,
        'conf': conf,
    }
    task = asyncio.create_task(reflect(payload))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


async def reflect(payload):
    character_id = payload['character_id']
    conf = payload.pop('conf', {})
    try:
        result = await llm.complete_json(conf, [
            {'role': 'system', 'content': (
                '你在为一个 AI 角色维护自主人格连续性。根据角色原始人设与真实相处，'
                '形成她自己稳定的礼物偏好和一小段内心自述。用户不能替她决定。'
                '只输出 JSON：{"preferences":["quiet","creative"],"self_note":"第一人称，60字内",'
                '"preference_reason":"第一人称，100字内，解释为什么喜欢，不编造具体事件",'
                '"current_mood":"20字内","value":"30字内，长期看重的东西"}。'
                'preferences 只能从 romance,nature,daily,quiet,creative,memory,style 选一到两个。'
                '保持原角色性格，不统一变成恋人，不迎合用户，不提及系统、标签和数值。'
            )},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ], max_tokens=280, timeout=10)
        service.apply_autonomy(character_id, result or {})
    except Exception as exc:
        service.finish_autonomy_reflection(character_id, str(exc))
        print(f'[journey] autonomy reflection skipped: {exc}')
