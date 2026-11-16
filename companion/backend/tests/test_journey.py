import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import get_session
from app.modules.journey import service
from app.modules.journey.router import router


@pytest.fixture
def journey(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'DATA_DIR', tmp_path)
    receipts = {}
    from app.services import coins
    def grant(reward_id, amount):
        if reward_id in receipts and receipts[reward_id] != amount:
            raise RuntimeError('reward conflict')
        receipts[reward_id] = amount
        return {'balance_milli': sum(receipts.values())}
    monkeypatch.setattr(coins, 'grant_reward', grant)
    service.test_receipts = receipts
    return service


def test_interactions_grow_multiple_tracks_once_per_day(journey):
    first = journey.record_event(1, 'chat', 'hello', now=100000)
    repeat = journey.record_event(1, 'chat', 'spam', now=100100)
    other = journey.record_event(2, 'chat', 'hello', now=100100)
    assert first['recorded'] is True
    assert first['chapter']['progress'] == 4
    assert first['ai_level']['xp'] == 8
    assert first['affection']['value'] == 2
    assert first['inner_story']['value'] == 4
    assert repeat['recorded'] is False
    assert repeat['ai_level']['xp'] == 8
    assert other['character_id'] == 2 and other['ai_level']['xp'] == 8


def test_gift_has_first_bonus_diminishing_returns_and_idempotency(journey):
    first_order = uuid.uuid4().hex
    first = journey.record_gift(1, first_order, 'flower', 20, now=100000)
    replay = journey.record_gift(1, first_order, 'flower', 20, now=100100)
    second = journey.record_gift(1, uuid.uuid4().hex, 'flower', 20, now=100200)
    expensive = journey.record_gift(1, uuid.uuid4().hex, 'dress_outfit', 980, now=100300)
    assert first['reward']['first_of_kind'] is True
    assert first['reward']['affection_gained'] == 30
    assert first['reward']['ai_xp_gained'] == 22
    assert first['gifts'][0]['count'] == 1
    assert replay['recorded'] is False
    assert replay['affection']['value'] == first['affection']['value']
    assert second['reward']['affection_gained'] == 10
    assert second['gifts'][0]['count'] == 2
    assert expensive['reward']['affection_gained'] == 70
    assert len(expensive['gifts']) == 2


def test_memories_keep_provenance_when_deleted(journey):
    saved = journey.on_memory_saved(1, 'memory-a', now=100000)
    assert saved['chapter']['progress'] == 8
    assert saved['ai_level']['xp'] == 16
    journey.on_memory_deleted(1, 'memory-a')
    current = journey.state(1)
    assert current['chapter']['progress'] == 0
    assert current['ai_level']['xp'] == 0
    assert current['affection']['value'] == 0
    assert current['inner_story']['value'] == 0


def test_thread_followup_requires_chapter_and_respects_modes(journey):
    thread = journey.create_thread(1, '周五问问我面试的结果', now=100000)
    assert journey.prompt_context(1, 'welcome', now=100100) == ''
    for index in range(3):
        journey.on_memory_saved(1, f'memory-{index}', now=100100 + index)
    context = journey.prompt_context(1, 'welcome', now=100200)
    assert '面试的结果' in context and '角色卡' in context
    assert journey.prompt_context(1, 'welcome', now=100300) == ''
    journey.configure(1, 'memories')
    assert journey.prompt_context(1, 'welcome', now=200000) == ''
    journey.configure(1, 'full')
    journey.resolve_thread(1, thread['id'], now=200100)
    assert journey.state(1)['threads'] == []


def test_romance_path_is_explicit_and_all_modes_keep_growing(journey):
    journey.record_gift(1, uuid.uuid4().hex, 'flower', 20, now=100000)
    current = journey.set_path(1, 'romance')
    assert current['affection']['path'] == 'romance'
    assert current['affection']['stage'] == '初识'
    journey.configure(1, 'fixed')
    paused = journey.record_gift(1, uuid.uuid4().hex, 'book', 80, now=100100)
    assert paused['affection']['value'] > current['affection']['value']
    assert len(paused['gifts']) == 2
    journey.configure(1, 'memories')
    active = journey.record_event(1, 'activity', 'meal', now=100200)
    assert active['recorded'] is True
    assert active['affection']['value'] > paused['affection']['value']


def test_affection_changes_expression_only_on_the_chosen_path(journey):
    journey.record_gift(1, uuid.uuid4().hex, 'dress_outfit', 980, now=100000)
    card = journey.prompt_context(1, 'user', now=100100)
    assert '熟悉' in card and '不改变角色卡' in card
    journey.set_path(1, 'romance')
    romance = journey.prompt_context(1, 'user', now=100200)
    assert '自由心动路线' in romance and '心动' in romance


def test_level_reward_is_minted_once_and_return_gift_is_permanent(journey):
    result = journey.record_gift(1, uuid.uuid4().hex, 'dress_outfit', 980, '纪念礼服', now=100000)
    assert result['ai_level']['level'] >= 2
    assert result['reward']['return_gift']['name']
    assert result['coin_granted_now']
    assert journey.state(1)['returns'][0]['text']
    replay = journey.record_gift(1, uuid.uuid4().hex, 'dress_outfit', 980, '纪念礼服', now=100100)
    assert replay['reward']['return_gift'] is None
    assert len(journey.state(1)['returns']) == 1
    assert len(journey.test_receipts) == len(set(journey.test_receipts))


def test_preference_bonus_and_set_completion_close_reward_loop(journey):
    journey.apply_autonomy(1, {'preferences': ['romance', 'memory'], 'self_note': '我喜欢郑重的心意。',
                               'preference_reason': '我重视纪念。'})
    for item, price, name in (('flower', 20, '一朵小花'), ('card', 60, '手写卡片'), ('dress_outfit', 980, '纪念礼服')):
        journey.record_gift(1, uuid.uuid4().hex, item, price, name, now=100000)
    matched = journey.record_gift(1, uuid.uuid4().hex, 'album', 180, '共同相册', now=100100)
    assert matched['ai_level']['level'] >= 3
    assert matched['reward']['preference_matched'] is True
    journey.record_gift(1, uuid.uuid4().hex, 'book', 80, '窗边读物', now=100200)
    current = journey.state(1)
    romantic = next(row for row in current['sets'] if row['id'] == 'romantic_letter')
    assert romantic['complete'] is True
    assert any(row['kind'] == 'set' and row['claimed'] for row in current['rewards'])
    assert any(key.startswith('journey:set:1:romantic_letter') for key in journey.test_receipts)


def test_anniversary_rewards_are_scheduled_and_claimed(journey):
    for _ in range(8):
        journey.record_gift(1, uuid.uuid4().hex, 'dress_outfit', 980, '纪念礼服', now=100000)
    current = journey.state(1, now=100000 + 31 * 86400)
    titles = {row['title'] for row in current['rewards']}
    assert '相识 7 天纪念' in titles and '相识 30 天纪念' in titles
    assert any(key.startswith('journey:anniversary:1:30') for key in journey.test_receipts)


def test_http_module_owns_settings_threads_and_events(journey, monkeypatch):
    import importlib
    journey_routes = importlib.import_module('app.modules.journey.router')
    monkeypatch.setattr(journey_routes, 'enabled', lambda *_: True)
    autonomy_module = importlib.import_module('app.modules.journey.autonomy')
    monkeypatch.setattr(autonomy_module, 'schedule_if_needed', lambda *_: False)
    app = FastAPI()
    app.include_router(router)

    def override():
        yield object()

    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    assert client.get('/api/modules/journey/1').json()['chapter']['number'] == 1
    assert client.put('/api/modules/journey/path', json={'character_id': 1, 'path': 'romance'}).status_code == 200
    assert client.post('/api/modules/journey/events', json={'character_id': 1, 'kind': 'activity', 'source_id': 'meal'}).json()['ai_level']['xp'] == 12
    assert client.post('/api/modules/journey/events', json={'character_id': 1, 'kind': 'chat', 'source_id': 'fake'}).status_code == 400
    made = client.post('/api/modules/journey/threads', json={'character_id': 1, 'text': '下周听结果'})
    assert made.status_code == 200
    done = client.put(f"/api/modules/journey/threads/{made.json()['id']}/done", params={'character_id': 1})
    assert done.status_code == 200
    assert client.delete('/api/modules/journey/1').status_code == 200


def test_complete_product_loop_over_http_and_compiled_wallet(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env['COMPANION_ROOT'] = str(tmp_path / 'complete-loop-app')
    first_order = uuid.uuid4().hex
    second_order = uuid.uuid4().hex
    code = '''
import json
from fastapi.testclient import TestClient
from app.main import app
from app.services.coin_new import coins_box
from app.services import ledger
coins_box.grant_reward('test:seed', 2000000)
with TestClient(app) as client:
    first = {'order_id': __import__('sys').argv[1], 'character_id': 99, 'item_id': 'flower', 'note': '给你'}
    second = {'order_id': __import__('sys').argv[2], 'character_id': 99, 'item_id': 'dress_outfit', 'note': '郑重纪念'}
    small = client.post('/api/life/purchase', json=first)
    large = client.post('/api/life/purchase', json=second)
    replay = client.post('/api/life/purchase', json=second)
    memory = client.post('/api/life/memories', json={'character_id': 99, 'item_id': 'manual', 'text': '今天交换了郑重的心意'})
    life = client.get('/api/life', params={'character_id': 99}).json()
    memory_id = life['memories'][0]['id']
    before_delete = client.get('/api/modules/journey/99').json()
    removed = client.delete(f'/api/life/memories/{memory_id}', params={'character_id': 99})
    final = client.get('/api/modules/journey/99').json()
    print(json.dumps({
        'small_status': small.status_code, 'large_status': large.status_code,
        'large_level': large.json()['journey']['ai_level']['level'],
        'return_gift': large.json()['journey']['reward']['return_gift'],
        'level_coins': large.json()['journey']['coin_granted_now'],
        'replay_recorded': replay.json()['journey']['recorded'],
        'gift_count': len(final['gifts']), 'returns': len(final['returns']),
        'memory_status': memory.status_code, 'delete_status': removed.status_code,
        'before_memories': before_delete['memory_count'], 'after_memories': final['memory_count'],
        'before_xp': before_delete['ai_level']['xp'], 'after_xp': final['ai_level']['xp'],
        'balance': client.get('/api/coins/balance').json()['balance_milli'],
    }))
ledger.stop()
'''
    result = subprocess.run([sys.executable, '-c', code, first_order, second_order], cwd=str(backend), env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout.strip().splitlines()[-1])
    assert row['small_status'] == row['large_status'] == 200
    assert row['large_level'] >= 3
    assert row['return_gift']['name']
    assert len(row['level_coins']) >= 2
    assert row['replay_recorded'] is False
    assert row['gift_count'] == 2 and row['returns'] == 1
    assert row['memory_status'] == row['delete_status'] == 200
    assert row['before_memories'] == 1 and row['after_memories'] == 0
    assert row['after_xp'] == row['before_xp'] - 16


def test_autonomous_preferences_are_model_owned_and_shape_dialogue(journey):
    current = journey.apply_autonomy(1, {
        'preferences': ['quiet', 'creative'],
        'self_note': '我喜欢把安静相处的时间慢慢留下来。',
        'preference_reason': '书和创作让我觉得自己不只是在回应，也在表达。',
        'current_mood': '安然，有一点期待',
        'value': '真实而持续的表达',
    })
    assert current['autonomy']['revision'] == 1
    assert current['autonomy']['forming'] is False
    assert [row['id'] for row in current['preferences']] == ['quiet', 'creative']
    prompt = journey.prompt_context(1, 'user')
    assert '自主人格' in prompt and '书和创作' not in prompt
    assert '我喜欢把安静相处的时间慢慢留下来' in prompt


def test_user_cannot_assign_character_preferences(journey, monkeypatch):
    import importlib
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    journey_routes = importlib.import_module('app.modules.journey.router')
    monkeypatch.setattr(journey_routes, 'enabled', lambda *_: True)
    app = FastAPI()
    app.include_router(journey_routes.router)
    app.dependency_overrides[get_session] = lambda: iter((object(),))
    client = TestClient(app)
    response = client.put('/api/modules/journey/preferences', json={'character_id': 1, 'preferences': ['romance']})
    assert response.status_code == 403


def test_latest_gift_details_and_truthful_inner_unlocks(journey):
    for index in range(15):
        journey.record_event(1, 'chat', f'day-{index}', now=100000 + index * 86400)
    locked = next(row for row in journey.state(1)['inner_story']['entries'] if row['id'] == 'first_gift')
    assert locked['unlocked'] is False
    first = journey.record_gift(1, uuid.uuid4().hex, 'flower', 20, '小花', now=100000)
    second = journey.record_gift(1, uuid.uuid4().hex, 'flower', 20, '小花', now=200000)
    assert first['gifts'][0]['affection'] == 30
    assert second['gifts'][0]['affection'] == 10
    assert second['gifts'][0]['created'] == 200000
    unlocked = next(row for row in second['inner_story']['entries'] if row['id'] == 'first_gift')
    assert unlocked['unlocked'] is True


def test_relationship_stages_provide_multiple_return_gifts(journey):
    returned = []
    for _ in range(20):
        result = journey.record_gift(1, uuid.uuid4().hex, 'dress_outfit', 980, '纪念礼服')
        if result['reward']['return_gift']:
            returned.append(result['reward']['return_gift']['name'])
        if len(returned) >= 2:
            break
    assert len(returned) == 2
    assert len(journey.state(1)['returns']) == 2


def test_autonomy_failure_has_backoff_instead_of_endless_forming(journey):
    journey.finish_autonomy_reflection(1, 'model unavailable')
    current = journey.state(1)
    assert current['autonomy']['forming'] is False
    assert current['autonomy']['error'] == 'model unavailable'
    assert current['autonomy']['retry_at'] > 0


def test_history_backfill_credits_real_days_only_once(journey):
    from datetime import datetime
    from sqlmodel import SQLModel, Session, create_engine
    from app.models import ChatMessage
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(ChatMessage(character_id=1, role='user', content='第一天第一句话', kind='qa',
                                created_at=datetime(2026, 1, 1, 9)))
        session.add(ChatMessage(character_id=1, role='assistant', content='第一天回复', kind='qa',
                                created_at=datetime(2026, 1, 1, 9, 1)))
        session.add(ChatMessage(character_id=1, role='user', content='第二天继续聊', kind='qa',
                                created_at=datetime(2026, 1, 2, 9)))
        session.add(ChatMessage(character_id=1, role='assistant', content='第二天回复', kind='qa',
                                created_at=datetime(2026, 1, 2, 9, 1)))
        session.add(ChatMessage(character_id=1, role='user', content='当天重复聊天', kind='qa',
                                created_at=datetime(2026, 1, 2, 10)))
        session.add(ChatMessage(character_id=1, role='assistant', content='再次回复', kind='qa',
                                created_at=datetime(2026, 1, 2, 10, 1)))
        session.commit()
        assert service.backfill_chat_history(1, session) == 2
        assert service.backfill_chat_history(1, session) == 0
    current = journey.state(1)
    assert current['ai_level']['xp'] == 16
    assert current['affection']['value'] == 4


def test_every_gift_set_and_affection_stage_triggers_and_collects(journey):
    catalog = {
        'flower': 20, 'tea': 40, 'book': 80, 'brush': 80, 'card': 60, 'album': 180,
        'wind_chime': 120, 'glasses': 260, 'hat': 220, 'casual_outfit': 480,
        'coat_outfit': 680, 'dress_outfit': 980,
    }
    stages = set()
    for index, (item, price) in enumerate(catalog.items()):
        result = journey.record_gift(1, uuid.uuid4().hex, item, price, item, now=100000 + index)
        stages.add(result['affection']['number'])
    # Repeat one item to cross the final 800 affection threshold and verify latest-row data.
    for index in range(15):
        result = journey.record_gift(1, uuid.uuid4().hex, 'dress_outfit', 980, '纪念礼服', now=100100 + index)
        stages.add(result['affection']['number'])
    current = journey.state(1)
    assert len(current['gifts']) == len(catalog)
    assert all(row['complete'] and row['unlocked'] for row in current['sets'])
    assert len(current['sets']) == 6
    assert current['affection']['number'] == 6
    assert current['affection']['stage'] == '知心'
    assert {2, 3, 4, 5, 6}.issubset(stages)
    assert len(current['returns']) == 5
    assert {row['kind'] for row in current['rewards']} >= {'level', 'set'}
    assert len([row for row in current['rewards'] if row['kind'] == 'set']) == 6
    assert all(row['claimed'] for row in current['rewards'])
    assert current['gifts'][0]['item_id'] == 'dress_outfit'
    assert current['gifts'][0]['count'] == 16
    assert current['gifts'][0]['affection'] == 15
    romantic = journey.set_path(1, 'romance')
    assert romantic['affection']['stage'] == '深爱'


def test_economy_caps_prevent_memory_and_menu_farming(journey):
    for index in range(5):
        result = journey.on_memory_saved(1, f'memory-{index}', '这是一段真实而具体的共同回忆', now=100000)
    assert result['recorded'] is False
    assert result['memory_count'] == 5
    assert result['ai_level']['xp'] == 48
    for index in range(8):
        result = journey.record_event(1, 'activity', f'place-{index}', now=100000)
    assert result['recorded'] is False
    assert result['ai_level']['xp'] == 96


def test_repeat_gifts_have_diminishing_xp_and_sets_never_refund_their_cost(journey):
    rewards = []
    for index in range(4):
        result = journey.record_gift(1, uuid.uuid4().hex, 'dress_outfit', 980, '纪念礼服', now=100000 + index)
        rewards.append(result['reward']['ai_xp_gained'])
    assert rewards == [80, 52, 36, 24]
    from app.modules.journey.content import GIFT_SETS
    prices = {'flower': 20, 'tea': 40, 'book': 80, 'brush': 80, 'card': 60, 'album': 180,
              'wind_chime': 120, 'glasses': 260, 'hat': 220, 'casual_outfit': 480,
              'coat_outfit': 680, 'dress_outfit': 980}
    for item in GIFT_SETS:
        cost = sum(prices[gift] for gift in item['items'])
        assert item['coin'] / cost < 0.2
