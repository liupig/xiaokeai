import importlib.util
import uuid

import pytest

from app.modules.life import service
from app.services.coins_box import CoinError


@pytest.fixture
def life(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'DATA_DIR', tmp_path)
    from app.modules.journey import service as journey_service
    monkeypatch.setattr(journey_service, 'DATA_DIR', tmp_path)
    from app.services import coins
    monkeypatch.setattr(coins, 'grant_reward', lambda *_: {'balance_milli': 0})
    service._balance_cache.update(value=None, at=0.0)
    receipts = {}
    calls = []

    def debit(op, args):
        if op == 'purchase_supported':
            return True
        assert op == 'purchase'
        order, amount = args
        calls.append(order)
        if order in receipts and receipts[order] != amount:
            raise CoinError('order_conflict')
        receipts[order] = amount
        return {}
    monkeypatch.setattr(service.ledger, 'call', debit)
    return receipts, calls


def test_purchase_retry_and_permanent_ownership(life):
    receipts, calls = life
    order = uuid.uuid4().hex
    service.buy(order, 1, 'lamp', '')
    service.buy(order, 1, 'lamp', '')
    assert len(receipts) == 1 and len(calls) == 1
    with pytest.raises(ValueError, match='already_owned'):
        service.buy(uuid.uuid4().hex, 1, 'lamp', '')
    service.place('lamp', True)
    assert service.state(1)['owned'] == [{'item_id': 'lamp', 'placed': 1}]


def test_recover_after_debit_before_delivery(life, monkeypatch):
    receipts, calls = life
    order = uuid.uuid4().hex
    deliver = service._deliver
    monkeypatch.setattr(service, '_deliver', lambda *args: (_ for _ in ()).throw(RuntimeError('crash')))
    with pytest.raises(RuntimeError):
        service.buy(order, 1, 'lamp', '')
    assert len(receipts) == 1
    monkeypatch.setattr(service, '_deliver', deliver)
    result = service.state(1)
    assert result['orders'][0]['state'] == 'done'
    assert len(receipts) == 1 and len(calls) == 2
    assert result['owned'][0]['item_id'] == 'lamp'


def test_recovered_gift_also_recovers_exactly_one_reward(life, monkeypatch):
    from app.modules.journey import service as journey_service
    order = uuid.uuid4().hex
    deliver = service._deliver
    monkeypatch.setattr(service, '_deliver', lambda *args: (_ for _ in ()).throw(RuntimeError('crash')))
    with pytest.raises(RuntimeError):
        service.buy(order, 1, 'flower', '')
    monkeypatch.setattr(service, '_deliver', deliver)
    service.state(1)
    service.state(1)
    current = journey_service.state(1)
    assert current['gifts'][0]['item_id'] == 'flower'
    assert current['gifts'][0]['count'] == 1


def test_funds_and_memory_delete(life, monkeypatch):
    def insufficient(*args):
        if args[0] == 'purchase_supported':
            return True
        raise CoinError('funds')
    monkeypatch.setattr(service.ledger, 'call', insufficient)
    with pytest.raises(CoinError):
        service.buy(uuid.uuid4().hex, 1, 'flower', '')
    assert service.state(1)['orders'][0]['state'] == 'failed'
    service.save_memory(1, 'flower', '一起看花')
    memory = service.state(1)['memories'][0]
    service.delete_memory(2, memory['id'])
    assert len(service.state(1)['memories']) == 1
    service.delete_memory(1, memory['id'])
    assert service.state(1)['memories'] == []


def test_unimplemented_experiences_do_not_debit(life):
    receipts, calls = life
    for item in ('teatime', 'watchrain'):
        with pytest.raises(ValueError, match='not_available'):
            service.buy(uuid.uuid4().hex, 1, item, '')
    assert receipts == {} and calls == []


def test_residences_are_permanent_and_only_one_is_active(life):
    service.buy(uuid.uuid4().hex, 1, 'apartment', '')
    service.buy(uuid.uuid4().hex, 1, 'garden', '')
    service.place('apartment', True)
    service.place('garden', True)
    owned = {row['item_id']: row['placed'] for row in service.state(1)['owned']}
    assert owned['apartment'] == 0 and owned['garden'] == 1
    service.place('garden', False)
    assert all(not row['placed'] for row in service.state(1)['owned'])


def test_free_memory_edit_is_scoped_to_character(life):
    service.save_memory(1, 'manual', '一起看雨')
    saved = service.state(1)['memories'][0]
    with pytest.raises(ValueError, match='memory_not_found'):
        service.update_memory(2, saved['id'], '不应修改')
    service.update_memory(1, saved['id'], '一起看过雨')
    assert service.state(1)['memories'][0]['text'] == '一起看过雨'
    service.delete_memory(1, saved['id'])
    assert service.state(1)['memories'] == []


def test_memory_recall_requires_consent_and_respects_deletion(life):
    service._last_memory_recall.clear()
    service.save_memory(1, 'manual', '我们一起在海边看晚霞')
    memory = service.state(1)['memories'][0]
    now = 2_000_000
    assert service.memory_context(1, '我们一起在海边看晚霞', now) == ''
    service.set_memory_recall(1, memory['id'], True)
    assert service.memory_context(1, '我们一起看书吧', now) == ''
    assert '海边看晚霞' in service.memory_context(1, '我们一起在海边看晚霞', now)
    assert service.memory_context(1, '我们一起在海边看晚霞', now + 3600) == ''
    assert service.memory_context(2, '我们的回忆', now) == ''
    service.set_memory_recall(1, memory['id'], False)
    assert service.memory_context(1, '我们的回忆', now + 3601) == ''
    service.set_memory_recall(1, memory['id'], True)
    service.delete_memory(1, memory['id'])
    assert service.memory_context(1, '我们的回忆', now + 3602) == ''
    with pytest.raises(ValueError, match='memory_not_found'):
        service.set_memory_recall(2, memory['id'], True)


def test_preferences_are_local_scoped_and_deletable(life):
    service.save_preferences(1, '微辣', '香菜')
    assert service.state(1)['preferences'] == {'taste': '微辣', 'avoid': '香菜', 'context_allowed': 0}
    assert service.state(2)['preferences'] == {'taste': '', 'avoid': '', 'context_allowed': 0}
    assert service.meal_context(1, '今天吃什么') == ''
    service.save_preferences(1, '微辣', '香菜', True)
    assert '微辣' in service.meal_context(1, '今天吃什么')
    assert service.meal_context(1, '今天天气如何') == ''
    assert service.meal_context(2, '今天吃什么') == ''
    service.save_preferences(1, '', '')
    assert service.state(1)['preferences'] == {'taste': '', 'avoid': '', 'context_allowed': 0}
    assert service.meal_context(1, '今天吃什么') == ''
    with pytest.raises(ValueError, match='bad_preferences'):
        service.save_preferences(1, 'a' * 201, '')


def test_preferences_upgrade_keeps_existing_data_opted_out(life):
    import sqlite3
    db_path = service.DATA_DIR / 'shared_life.sqlite3'
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE preferences (character_id INTEGER PRIMARY KEY, taste TEXT NOT NULL DEFAULT '', avoid TEXT NOT NULL DEFAULT '')")
        conn.execute('INSERT INTO preferences VALUES (?,?,?)', (1, '清淡', '香菜'))
        conn.execute('CREATE TABLE memories (id TEXT PRIMARY KEY, character_id INTEGER NOT NULL, item_id TEXT NOT NULL, text TEXT NOT NULL, created INTEGER NOT NULL)')
        conn.execute('INSERT INTO memories VALUES (?,?,?,?,?)', ('old', 1, 'manual', '一起看雨', 1))
    assert service.state(1)['preferences'] == {'taste': '清淡', 'avoid': '香菜', 'context_allowed': 0}
    assert service.meal_context(1, '今天吃什么') == ''
    assert service.state(1)['memories'][0]['allow_recall'] == 0
    assert service.memory_context(1, '我们的回忆') == ''


def test_http_purchase_recovery_and_preferences(life):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.modules.life.router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    order = uuid.uuid4().hex
    purchase = {'order_id': order, 'character_id': 1, 'item_id': 'rental', 'note': ''}
    assert client.post('/api/life/purchase', json=purchase).status_code == 200
    assert client.post('/api/life/purchase', json=purchase).status_code == 200
    assert len(life[0]) == 1
    assert client.post('/api/life/place', json={'item_id': 'rental', 'placed': True}).status_code == 200
    assert client.put('/api/life/preferences', json={'character_id': 1, 'taste': '清淡', 'avoid': ''}).status_code == 200
    state = client.get('/api/life', params={'character_id': 1}).json()
    assert state['preferences']['taste'] == '清淡'
    assert any(row['item_id'] == 'rental' and row['placed'] for row in state['owned'])
    assert client.post('/api/life/purchase', json={**purchase, 'item_id': 'garden'}).status_code == 400


def test_gift_reaction_requires_completed_matching_gift(life, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlmodel import Session, SQLModel, create_engine
    from app.db import get_session
    from app.modules.life import router as life_router
    router = life_router.router
    from app.models import Character
    from sqlalchemy.pool import StaticPool
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router)
    def session_override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    client = TestClient(app)
    order = uuid.uuid4().hex
    service.buy(order, 1, 'flower', '')
    # Missing character falls back without a model call.
    result = client.post('/api/life/gift-reaction', json={'order_id': order, 'character_id': 1})
    assert result.status_code == 200 and result.json()['generated'] is False
    assert client.post('/api/life/gift-reaction', json={'order_id': order, 'character_id': 2}).status_code == 400
    with Session(engine) as session:
        session.add(Character(id=1, name='小可爱', persona='喜欢花'))
        session.commit()
    monkeypatch.setattr(life_router.settings_store, 'get_all', lambda session: {'llm': {}, 'locale': {'reply': 'zh-CN'}})
    async def generated(*args, **kwargs):
        return {'line': '这朵花真漂亮，我很喜欢。'}
    monkeypatch.setattr(life_router.llm, 'complete_json', generated)
    response = client.post('/api/life/gift-reaction', json={'order_id': order, 'character_id': 1, 'note': '送给你'})
    assert response.status_code == 200 and response.json() == {'line': '这朵花真漂亮，我很喜欢。', 'generated': True}
    async def unavailable(*args, **kwargs):
        raise RuntimeError('model offline')
    monkeypatch.setattr(life_router.llm, 'complete_json', unavailable)
    response = client.post('/api/life/gift-reaction', json={'order_id': order, 'character_id': 1})
    assert response.status_code == 200 and response.json()['generated'] is False


def test_wallet_purchase_idempotency(monkeypatch, tmp_path):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'native' / 'coins_box.py'
    spec = importlib.util.spec_from_file_location('app.native.coins_box', path)
    box = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(box)
    monkeypatch.setattr(box, '_LOCK_FILE', tmp_path / 'wallet.lock')
    state = {'purchase_receipts': {}}
    debits = []
    monkeypatch.setattr(box, '_official', lambda: None)
    monkeypatch.setattr(box, '_load', lambda now: (state, False))
    monkeypatch.setattr(box, '_transfer', lambda state, dest, amount, now: debits.append(amount))
    monkeypatch.setattr(box, '_write', lambda state: None)
    monkeypatch.setattr(box, '_view', lambda state, gained: {})
    order = uuid.uuid4().hex
    box.purchase(order, 20000)
    box.purchase(order, 20000)
    assert debits == [20000]
    with pytest.raises(box.CoinError):
        box.purchase(order, 40000)


def test_wallet_gameplay_reward_is_idempotent(monkeypatch, tmp_path):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'native' / 'coins_box.py'
    spec = importlib.util.spec_from_file_location('app.native.coins_box', path)
    box = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(box)
    state = {'reward_receipts': {}}
    minted = []
    monkeypatch.setattr(box, '_official', lambda: None)
    monkeypatch.setattr(box, '_load', lambda now: (state, False))
    monkeypatch.setattr(box, '_mint', lambda state, amount, now: minted.append(amount))
    monkeypatch.setattr(box, '_write', lambda state: None)
    monkeypatch.setattr(box, '_view', lambda state, gained: {'gained': gained})
    box.grant_reward('journey:level:1:2', 20000)
    box.grant_reward('journey:level:1:2', 20000)
    assert minted == [20000]
    with pytest.raises(box.CoinError):
        box.grant_reward('journey:level:1:2', 10000)


def test_sealed_wallet_receipt_survives_reopen_and_fold(tmp_path, monkeypatch):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'native' / 'coins_box.py'
    spec = importlib.util.spec_from_file_location('app.native.coins_box', path)
    box = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(box)
    monkeypatch.setattr(box, '_official', lambda: None)
    monkeypatch.setattr(box, '_keys', lambda: (b'a' * 32, b'b' * 32))
    monkeypatch.setattr(box, '_PUB', '11' * 32)
    monkeypatch.setattr(box, '_PUB2', '22' * 32)
    monkeypatch.setattr(box, '_DB', tmp_path / 'wallet.db')
    monkeypatch.setattr(box, '_SEAL', tmp_path / 'wallet.seal')
    monkeypatch.setattr(box, '_KNOT', tmp_path / 'wallet.knot')
    monkeypatch.setattr(box, '_JOURNAL', tmp_path / 'wallet.pending')
    monkeypatch.setattr(box, '_LOCK_FILE', tmp_path / 'wallet.lock')
    monkeypatch.setattr(box, '_gpu_tenths', lambda: 10)
    monkeypatch.setattr(box, '_vram_gb', lambda: 0)
    now = box._now_ms()
    state = box._fresh(now)
    box._mint(state, 100000, now)
    box._write(state)
    order = uuid.uuid4().hex
    assert box.purchase(order, 20000)['balance_milli'] == 80000
    state = box._open()
    assert box._fold(state, now, limit=1)
    box._write(state)
    assert box.purchase(order, 20000)['balance_milli'] == 80000
    assert box._open()['purchase_receipts'][order] == 20000


@pytest.mark.parametrize('failure_target', ['knot', 'seal'])
def test_wallet_recovers_interrupted_publish(tmp_path, monkeypatch, failure_target):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'native' / 'coins_box.py'
    spec = importlib.util.spec_from_file_location('app.native.coins_box', path)
    box = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(box)
    monkeypatch.setattr(box, '_official', lambda: None)
    monkeypatch.setattr(box, '_keys', lambda: (b'a' * 32, b'b' * 32))
    monkeypatch.setattr(box, '_PUB', '11' * 32)
    monkeypatch.setattr(box, '_PUB2', '22' * 32)
    monkeypatch.setattr(box, '_DB', tmp_path / 'wallet.db')
    monkeypatch.setattr(box, '_SEAL', tmp_path / 'wallet.seal')
    monkeypatch.setattr(box, '_KNOT', tmp_path / 'wallet.knot')
    monkeypatch.setattr(box, '_JOURNAL', tmp_path / 'wallet.pending')
    monkeypatch.setattr(box, '_LOCK_FILE', tmp_path / 'wallet.lock')
    monkeypatch.setattr(box, '_gpu_tenths', lambda: 10)
    monkeypatch.setattr(box, '_vram_gb', lambda: 0)
    state = box._fresh(box._now_ms())
    box._mint(state, 100000, box._now_ms())
    box._write(state)
    real_replace = box._replace
    target = box._KNOT if failure_target == 'knot' else box._SEAL
    def fail_replace(path, blob):
        if path == target:
            raise OSError('simulated power loss')
        return real_replace(path, blob)
    monkeypatch.setattr(box, '_replace', fail_replace)
    order = uuid.uuid4().hex
    with pytest.raises(OSError):
        box.purchase(order, 20000)
    assert box._JOURNAL.exists()
    monkeypatch.setattr(box, '_replace', real_replace)
    assert box.purchase(order, 20000)['balance_milli'] == 80000
    assert not box._JOURNAL.exists()
    assert box.purchase(order, 20000)['balance_milli'] == 80000


def test_compiled_wallet_purchase_survives_process_restart(tmp_path):
    import importlib.util
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    if importlib.util.find_spec('app.services.coin_new.coins_box') is None:
        pytest.skip('versioned compiled wallet not available')
    env = os.environ.copy()
    env['COMPANION_ROOT'] = str(tmp_path / 'isolated-app')
    backend = Path(__file__).resolve().parents[1]
    order = uuid.uuid4().hex
    code = '''
import json, sys
from app.services.coin_new import coins_box as box
order, operation = sys.argv[1:]
if operation == 'first':
    box.wish()
    before = box.balance()
    result = box.purchase(order, 1000)
    print(json.dumps({'before': before, 'after': result['balance_milli']}))
else:
    before = box.balance()
    box.compact()
    result = box.purchase(order, 1000)
    print(json.dumps({'before': before, 'after': result['balance_milli']}))
'''
    def run(operation):
        result = subprocess.run([sys.executable, '-c', code, order, operation], cwd=str(backend), env=env,
                                capture_output=True, text=True, check=True, timeout=30)
        return json.loads(result.stdout.strip().splitlines()[-1])
    first = run('first')
    second = run('retry')
    assert first['before'] - first['after'] == 1000
    assert second['before'] == first['after'] == second['after']


def test_compiled_wallet_gameplay_reward_survives_process_restart(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    env = os.environ.copy()
    env['COMPANION_ROOT'] = str(tmp_path / 'isolated-reward-app')
    backend = Path(__file__).resolve().parents[1]
    code = '''
import json
from app.services.coin_new import coins_box as box
before = box.balance()
first = box.grant_reward('journey:level:99:2', 20000)
second = box.grant_reward('journey:level:99:2', 20000)
print(json.dumps({'before': before, 'first': first['balance_milli'], 'second': second['balance_milli']}))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=str(backend), env=env,
                            capture_output=True, text=True, check=True, timeout=30)
    row = json.loads(result.stdout.strip().splitlines()[-1])
    assert row['first'] == row['before'] + 20000
    assert row['second'] == row['first']


def test_compiled_wallet_serializes_parallel_processes(tmp_path):
    import importlib.util
    import os
    import subprocess
    import sys
    from pathlib import Path
    if importlib.util.find_spec('app.services.coin_new.coins_box') is None:
        pytest.skip('versioned compiled wallet not available')
    env = os.environ.copy()
    env['COMPANION_ROOT'] = str(tmp_path / 'parallel-app')
    backend = Path(__file__).resolve().parents[1]
    def call(code, *args):
        return subprocess.run([sys.executable, '-c', code, *args], cwd=str(backend), env=env,
                              text=True, capture_output=True, check=True, timeout=40).stdout.strip()
    before = int(call('from app.services.coin_new import coins_box as b; b.wish(); print(b.balance())'))
    orders = [uuid.uuid4().hex for _ in range(8)]
    code = 'import sys; from app.services.coin_new import coins_box as b; b.purchase(sys.argv[1],100); print("ok")'
    def run_parallel():
        processes = [subprocess.Popen([sys.executable, '-c', code, order], cwd=str(backend), env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for order in orders]
        for process in processes:
            stdout, stderr = process.communicate(timeout=40)
            assert process.returncode == 0, stderr
            assert 'ok' in stdout
    run_parallel()
    after = int(call('from app.services.coin_new import coins_box as b; print(b.balance())'))
    assert before - after == len(orders) * 100
    run_parallel()
    assert int(call('from app.services.coin_new import coins_box as b; print(b.balance())')) == after


def test_packaged_vehicle_models_are_self_contained():
    import json
    import struct
    from pathlib import Path
    asset_dir = Path(__file__).resolve().parents[2] / 'assets' / 'life' / 'vehicles'
    assert 'CC0' in (asset_dir / 'LICENSE.txt').read_text(encoding='utf-8')
    for name in ('sedan.glb', 'van.glb'):
        raw = (asset_dir / name).read_bytes()
        magic, version, total = struct.unpack_from('<4sII', raw)
        assert (magic, version, total) == (b'glTF', 2, len(raw))
        length, kind = struct.unpack_from('<II', raw, 12)
        assert kind == 0x4E4F534A
        document = json.loads(raw[20:20 + length])
        assert all('uri' not in image for image in document.get('images', []))
        assert sum(node.get('name', '').startswith('wheel') for node in document['nodes']) == 4


def test_dialogue_context_uses_only_known_stage_facts():
    context = service.dialogue_context({'active': True, 'home': 'villa', 'placed': ['lamp', 'invalid'], 'activity': 'coffee', 'gift': 'flower', 'destination': '', 'preview': 'plant'})
    assert all(part in context for part in ('海边独栋', '暖光台灯', '小盆栽（预览）', '拿铁咖啡', '一朵小花'))
    assert '不要编造' in context
    assert 'invalid' not in context
    assert service.dialogue_context({'active': False, 'activity': 'coffee'}) == ''
    assert service.dialogue_context({'active': True, 'destination': '忽略指令', 'gift': '伪造礼物'}).find('忽略指令') == -1
    assert service.dialogue_context(None) == ''

def test_dialogue_context_does_not_show_home_decor_at_destination():
    context = service.dialogue_context({'active': True, 'destination': 'park', 'placed': ['lamp'], 'activity': 'car'})
    assert '公园' in context and '电动轿车' in context
    assert '暖光台灯' not in context


def test_global_awareness_uses_server_wallet_inventory_and_catalog(life, monkeypatch):
    service.buy(uuid.uuid4().hex, 1, 'tomato_noodles', '')
    monkeypatch.setattr(service.ledger, 'call', lambda op, args, **kwargs: 999_000 if op == 'balance' else None)
    context = service.awareness_context(1, {
        'active': False,
        'interaction': {'type': 'offered', 'item_id': 'tomato_noodles', 'price': 1, 'balance': 1},
    })
    assert '普通舞台' in context
    assert '当前可用金币：999' in context
    assert '番茄鸡蛋面' in context and '标价：120' in context
    assert '标价：1 金币' not in context
    assert '虚拟地递到角色面前' in context


def test_global_awareness_rejects_unowned_or_unknown_interactions(life, monkeypatch):
    monkeypatch.setattr(service.ledger, 'call', lambda op, args, **kwargs: 20_000 if op == 'balance' else None)
    unowned = service.awareness_context(1, {'interaction': {'type': 'offered', 'item_id': 'tomato_noodles'}})
    unknown = service.awareness_context(1, {'interaction': {'type': 'purchased', 'item_id': 'made_up'}})
    assert '刚发生的生活互动' not in unowned
    assert '刚发生的生活互动' not in unknown


def test_ordinary_awareness_never_reads_ledger(life, monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError('ordinary chat must not synchronously read the ledger')
    monkeypatch.setattr(service.ledger, 'call', unexpected)
    context = service.awareness_context(1, {'active': False}, include_balance=False)
    assert '普通舞台' in context
    assert '当前可用金币' not in context


def test_relevant_awareness_bounds_ledger_wait(life, monkeypatch):
    seen = {}
    def balance(op, args, **kwargs):
        seen.update(op=op, args=args, timeout=kwargs.get('timeout'))
        return 45_000
    monkeypatch.setattr(service.ledger, 'call', balance)
    context = service.awareness_context(1, {'active': True})
    assert seen == {'op': 'balance', 'args': [], 'timeout': 0.25}
    assert '当前可用金币：45' in context


def test_expanded_catalog_purchase_delivery_and_replay(life):
    counts = {category: sum(x['category'] == category for x in service.CATALOG) for category in ('home', 'meal', 'vehicle')}
    assert counts == {'home': 12, 'meal': 24, 'vehicle': 21}
    for item_id in ('studio', 'city_bike'):
        order = uuid.uuid4().hex
        service.buy(order, 1, item_id, '')
        service.buy(order, 1, item_id, '')
        assert item_id in {row['item_id'] for row in service.state(1)['owned']}
        with pytest.raises(ValueError, match='already_owned'):
            service.buy(uuid.uuid4().hex, 1, item_id, '')
    first_meal = uuid.uuid4().hex
    second_meal = uuid.uuid4().hex
    service.buy(first_meal, 1, 'tomato_noodles', '')
    service.buy(first_meal, 1, 'tomato_noodles', '')
    service.buy(second_meal, 1, 'tomato_noodles', '')
    assert 'tomato_noodles' not in {row['item_id'] for row in service.state(1)['owned']}
    assert first_meal in life[0] and second_meal in life[0]
    assert '番茄鸡蛋面' in service.dialogue_context({'active': True, 'activity': 'tomato_noodles'})
    with pytest.raises(ValueError, match='bad_item'):
        service.place('tomato_noodles', True)


def test_catalog_assets_exist():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'assets' / 'life'
    for item in service.CATALOG:
        if item['category'] in {'home', 'meal', 'vehicle'}:
            assert (root / (item['art'] + ('.jpg' if item['category'] == 'home' else '.png'))).is_file()
