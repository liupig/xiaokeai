from app.locale_pack import normalize, detect_script, default_voice, voice_fits, compile_intent
from app.services import asr, asr_gigaam, tts_qwen
from app.services.speech_split import SentenceSplitter


def test_russian_language_and_qwen():
    assert normalize("ru-RU") == "ru"
    assert detect_script("\u041f\u0440\u0438\u0432\u0435\u0442, \u043a\u0430\u043a \u0434\u0435\u043b\u0430?") == "ru"
    assert tts_qwen.qwen_language("ru-RU") == "Russian"
    assert default_voice("qwen", "ru") == "Serena"
    assert voice_fits("qwen", "Serena", "ru")


def test_gigaam_files_and_missing_model(tmp_path, monkeypatch):
    monkeypatch.setattr(asr_gigaam, "MODEL_DIR", tmp_path)
    assert not asr_gigaam.model_ready()
    try:
        asr_gigaam.ensure_model(download=False)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing model should fail without downloading")
    assert asr.status("ru")["engine"] == "gigaam-v3"
    assert not asr.status("ru")["installed"]


def test_russian_sentence_split_keeps_words():
    splitter = SentenceSplitter("ru")
    text = "\u041f\u0440\u0438\u0432\u0435\u0442, \u043a\u0430\u043a \u0442\u0432\u043e\u0438 \u0434\u0435\u043b\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f?"
    assert "".join(splitter.feed(text) + splitter.flush()) == text
    long_word = 'достопримечательность'
    assert long_word in tts_qwen._utterances(long_word + ' прекрасная')[0]


def test_russian_intents_and_tarot_names():
    from app.modules.tarot.deck import display_name
    from app.modules.tarot.plays import match_play_id, spread_positions, get_play
    from app.locale_pack import set_reply
    assert compile_intent('ru', 'classify.dance').search('Потанцуй для меня')
    assert compile_intent('ru', 'wish.hint').search('Хочу загадать желание')
    assert compile_intent('ru', 'tarot.three').search('Вытащи три карты')
    assert compile_intent('ru', 'roleplay.enter').search('Будь учителем')
    assert display_name({'id': 'major/00-fool'}, 'ru') == 'Шут'
    assert display_name({'id': 'cups/01-ace', 'suit': 'cups'}, 'ru') == 'Туз Кубков'
    set_reply('ru')
    assert match_play_id('Вытащи три карты') == 'three'
    assert spread_positions(get_play('three')) == ['Прошлое', 'Настоящее', 'Будущее']
    set_reply('zh-CN')


def test_russian_ui_preserves_keys_and_interpolation():
    import json
    import re
    from pathlib import Path
    locales = Path(__file__).resolve().parents[2] / 'locales'
    english = json.loads((locales / 'en' / 'ui.json').read_text(encoding='utf-8'))
    russian = json.loads((locales / 'ru' / 'ui.json').read_text(encoding='utf-8'))
    assert set(english) <= set(russian)
    for key, value in english.items():
        assert set(re.findall(r'\{[^{}]+\}', value)) == set(re.findall(r'\{[^{}]+\}', russian[key])), key

def test_gigaam_recognizer_uses_transducer_and_resamples(monkeypatch, tmp_path):
    import io
    import wave
    import numpy as np
    import sherpa_onnx
    calls = {}
    class Stream:
        result = type('Result', (), {'text': ' test '})()
        def accept_waveform(self, rate, samples):
            calls['rate'] = rate
            calls['samples'] = len(samples)
    class Recognizer:
        def create_stream(self):
            return Stream()
        def decode_stream(self, stream):
            calls['decoded'] = True
    def create(**kwargs):
        calls.update(kwargs)
        return Recognizer()
    monkeypatch.setattr(asr_gigaam, '_recognizer', None)
    monkeypatch.setattr(asr_gigaam, 'ensure_model', lambda: None)
    monkeypatch.setattr(asr_gigaam, 'MODEL_DIR', tmp_path)
    monkeypatch.setattr(sherpa_onnx.OfflineRecognizer, 'from_transducer', create)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(np.zeros(800, dtype=np.int16).tobytes())
    assert asr_gigaam._transcribe_local(buf.getvalue()) == 'test'
    assert calls['model_type'] == 'nemo_transducer'
    assert calls['rate'] == 16000 and calls['samples'] == 1600
    assert calls['decoded']
