import asyncio
import queue
import threading

from app.services import tts_tera, tts
from app.locale_pack import align_voice


def test_voice_selection_and_language():
    assert tts.resolve_voice('tera', 'ru_f1') == 'ru_f1'
    assert align_voice('tera', 'ru_f2', 'ru') == 'ru_f2'
    assert len(tts_tera.VOICES) == 10
    assert align_voice('tera', 'eng_f3', 'ru') == 'eng_f3'


def test_missing_model_keeps_status_and_other_voices_available(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_tera, 'MODEL_DIR', tmp_path)
    assert tts_tera.status()['installed'] is False
    assert tts.resolve_voice('qwen', 'Serena') == 'Serena'
    assert tts.resolve_voice('tera', 'ru_f1') == 'ru_f1'
    monkeypatch.setattr(tts_tera, '_gpu_proc', None)
    try:
        tts_tera._ensure_gpu_worker()
    except FileNotFoundError as exc:
        assert 'download' in str(exc)
    else:
        raise AssertionError('Missing model should be reported before GPU startup')


def test_gpu_runtime_absent_is_reported_without_impacting_other_engines(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_tera, 'GPU_RUNTIME_DIR', tmp_path)
    monkeypatch.setattr(tts_tera, 'installed', lambda: True)
    monkeypatch.setattr(tts_tera, '_gpu_proc', None)
    assert tts_tera.status()['gpu_runtime'] is False
    try:
        tts_tera._ensure_gpu_worker()
    except RuntimeError as exc:
        assert 'GPU runtime missing' in str(exc)
    else:
        raise AssertionError('Missing GPU runtime must be reported explicitly')
    assert tts.resolve_voice('qwen', 'Serena') == 'Serena'


def test_missing_model_does_not_download(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_tera, 'MODEL_DIR', tmp_path)
    monkeypatch.setattr(tts_tera, '_model', None)
    assert not tts_tera.installed()
    try:
        tts_tera._load()
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('Missing model must not silently download')


def test_download_uses_pinned_revision_and_optional_directory(monkeypatch, tmp_path):
    import huggingface_hub
    received = {}
    def snapshot(repo, **kwargs):
        received.update(repo=repo, **kwargs)
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', snapshot)
    monkeypatch.setattr(tts_tera, 'MODEL_DIR', tmp_path)
    monkeypatch.setattr(tts_tera, 'installed', lambda: True)
    monkeypatch.setattr(tts_tera, '_rank_sources', lambda: [('Hugging Face', 'https://huggingface.co')])
    monkeypatch.setattr(tts_tera, '_verify_snapshot', lambda path: {})
    monkeypatch.setitem(tts_tera._state, 'downloading', True)
    tts_tera.download()
    assert received['repo'] == 'TeraSpace/TeraTTSv2'
    assert received['revision'] == tts_tera.REVISION
    assert received['local_dir'] == str(tmp_path.parent / (tmp_path.name + '-download'))
    assert received['endpoint'] == 'https://huggingface.co'
    assert not tts_tera._state['downloading']


def test_download_falls_back_after_source_failure(monkeypatch, tmp_path):
    import huggingface_hub
    calls = []
    def snapshot(repo, **kwargs):
        calls.append(kwargs['endpoint'])
        if len(calls) == 1:
            raise OSError('network unavailable')
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', snapshot)
    monkeypatch.setattr(tts_tera, 'MODEL_DIR', tmp_path)
    monkeypatch.setattr(tts_tera, 'installed', lambda: True)
    monkeypatch.setattr(tts_tera, '_verify_snapshot', lambda path: {})
    monkeypatch.setattr(tts_tera, '_rank_sources', lambda: [('Mirror', 'https://hf-mirror.com'), ('Hugging Face', 'https://huggingface.co')])
    tts_tera.download()
    assert calls == ['https://hf-mirror.com', 'https://huggingface.co']
    assert tts_tera.status()['source'] == 'Hugging Face'


def test_modelscope_source_requires_exact_model(monkeypatch):
    import io
    import json
    class Response(io.BytesIO):
        status = 200
    def response(model_id):
        return Response(json.dumps({'data': {'models': [{'id': model_id}]}}).encode())
    monkeypatch.setattr(tts_tera.urllib.request, 'urlopen', lambda *a, **kw: response('other/TeraTTSv2'))
    source = ('ModelScope', 'https://modelscope.cn')
    assert tts_tera._probe_source(source) == float('inf')
    monkeypatch.setattr(tts_tera.urllib.request, 'urlopen', lambda *a, **kw: response('TeraSpace/TeraTTSv2'))
    assert tts_tera._probe_source(source) != float('inf')


def test_checksum_failure_falls_back_without_touching_installed_model(monkeypatch, tmp_path):
    import huggingface_hub
    calls = []
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', lambda repo, **kwargs: calls.append(kwargs['endpoint']))
    monkeypatch.setattr(tts_tera, 'MODEL_DIR', tmp_path / 'installed')
    monkeypatch.setattr(tts_tera, 'installed', lambda: True)
    monkeypatch.setattr(tts_tera, '_rank_sources', lambda: [('Mirror', 'https://hf-mirror.com'), ('Hugging Face', 'https://huggingface.co')])
    def verify(path):
        if len(calls) == 1:
            raise tts_tera.SnapshotVerificationError('teratts.py', 'checksum mismatch')
        return {}
    monkeypatch.setattr(tts_tera, '_verify_snapshot', verify)
    tts_tera.download()
    assert calls == ['https://hf-mirror.com', 'https://huggingface.co']


def test_modelscope_snapshot_is_verified_before_use(monkeypatch, tmp_path):
    import importlib
    import huggingface_hub
    ms = importlib.import_module('modelscope.hub.snapshot_download')
    calls = []
    monkeypatch.setattr(ms, 'snapshot_download', lambda *a, **k: calls.append('modelscope'))
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', lambda *a, **k: calls.append('huggingface'))
    monkeypatch.setattr(tts_tera, 'MODEL_DIR', tmp_path / 'installed')
    monkeypatch.setattr(tts_tera, 'installed', lambda: True)
    monkeypatch.setattr(tts_tera, '_rank_sources', lambda: [('ModelScope', 'https://modelscope.cn'), ('Hugging Face', 'https://huggingface.co')])
    def verify(path):
        if len(calls) == 1:
            raise tts_tera.SnapshotVerificationError('teratts.py', 'checksum mismatch')
        return {}
    monkeypatch.setattr(tts_tera, '_verify_snapshot', verify)
    tts_tera.download()
    assert calls == ['modelscope', 'huggingface']


def test_stream_preserves_pcm_and_errors(monkeypatch):
    def produce(text, voice, cancelled, out, language):
        out.put(('audio', b'\x01\x02'))
        out.put(('end', None))
    monkeypatch.setattr(tts_tera, '_produce', produce)
    async def run():
        return [chunk async for chunk in tts_tera.synthesize_pcm('Привет', 'ru_f1', threading.Event())]
    assert asyncio.run(run()) == [b'\x01\x02']
    assert tts_tera.SAMPLE_RATE == 44100


def test_tts_route_streams_tera_at_native_rate(monkeypatch):
    from app.routers import speech
    conf = {'tts': {'engine': 'tera', 'voice': 'ru_f1'}, 'locale': {'reply': 'ru'}, 'llm': {}}
    monkeypatch.setattr(speech.settings_store, 'get_all', lambda _session: conf)
    monkeypatch.setattr(speech.settings_store, 'apply_llm_overlay', lambda value: value)
    async def fake_speech(text, voice, cancelled, language):
        assert voice == 'ru_f1'
        yield b'\x01\x02'
    monkeypatch.setattr(tts_tera, 'synthesize_pcm', fake_speech)
    class Session:
        def commit(self): pass
        def close(self): pass
    class Request:
        async def is_disconnected(self): return False
    async def run():
        response = await speech.tts_endpoint(speech.TTSRequest(text='Привет', engine='tera', voice='ru_f1'), Request(), Session())
        return response, b''.join([chunk async for chunk in response.body_iterator])
    response, pcm = asyncio.run(run())
    assert response.headers['X-Audio-Rate'] == '44100'
    assert pcm == b'\x01\x02'
