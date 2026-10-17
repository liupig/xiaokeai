"""阿里 / 火山语音：不联网，只核对组包和 Key 选择。"""
from __future__ import annotations

import gzip
import json
import os
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.locale_pack import align_voice, default_voice  # noqa: E402
from app.services import asr_ali, asr_volc, cloud_key, tts_volc  # noqa: E402


def test_keys_follow_the_chat_vendor():
    for name in (
        "DASHSCOPE_API_KEY", "ARK_API_KEY", "VOLC_ARK_API_KEY", "VOLC_SPEECH_API_KEY",
        "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY",
    ):
        os.environ.pop(name, None)
    ali = {"api_key": "sk-test", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}
    volc = {"api_key": "ark-test", "base_url": "https://ark.cn-beijing.volces.com/api/v3"}
    assert cloud_key.ali_key(ali) == "sk-test"
    assert cloud_key.volc_speech_key(volc) == "ark-test"
    assert cloud_key.ali_key(volc) == ""
    assert cloud_key.volc_speech_key(ali) == ""


def test_ali_body_is_a_data_url():
    body = asr_ali.request_body(b"RIFFxxxx")
    data = body["messages"][0]["content"][0]["input_audio"]["data"]
    assert data.startswith("data:audio/wav;base64,")
    assert body["model"] == "qwen3-asr-flash"
    assert asr_ali.text_of({"choices": [{"message": {"content": " 你好 "}}]}) == "你好"


def test_volc_frame_roundtrip():
    raw = gzip.compress(json.dumps({"result": {"text": "在吗"}}).encode("utf-8"))
    frame = asr_volc.pack_frame(0x9, 0x03, 0x1, 0x1, -2, raw)
    parsed = asr_volc.parse_frame(frame)
    assert parsed["last"] is True
    assert parsed["seq"] == -2
    assert asr_volc.text_of(parsed["json"]) == "在吗"


def test_volc_error_frame():
    msg = "denied".encode("utf-8")
    frame = bytes((0x11, 0xF0, 0x00, 0x00)) + struct.pack(">I", 401) + struct.pack(">I", len(msg)) + msg
    try:
        asr_volc.parse_frame(frame)
    except RuntimeError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("expected error")


def test_wav_stays_16k_pcm():
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 160)
    pcm = asr_volc.wav_to_pcm16_16k(buf.getvalue())
    assert len(pcm) == 320


def test_official_voice_packs_are_loaded():
    from app.services.tts_cosy import COSY_VOICES
    from app.services.tts_volc import VOLC_VOICES
    assert len(COSY_VOICES) == 88
    assert len(VOLC_VOICES) == 444
    assert any(v["id"] == "longhuhu_v3" for v in COSY_VOICES)
    assert any(v["id"] == "loongriko_v3" for v in COSY_VOICES)
    assert any(v["id"].startswith("ICL_uranus_") for v in VOLC_VOICES)
    kept = "ar_female_dina_uranus_bigtts"
    assert align_voice("volc", kept, "zh-CN") == kept


def test_volc_voice_follows_reply_language():
    assert default_voice("volc", "zh-CN") == "zh_female_vv_uranus_bigtts"
    assert default_voice("volc", "ja") == "ja_female_bv522_uranus_bigtts"
    assert align_voice("volc", "Serena", "zh-CN") == "zh_female_vv_uranus_bigtts"
    assert align_voice("volc", "en_female_dacey_uranus_bigtts", "en") == "en_female_dacey_uranus_bigtts"


def test_volc_tts_line():
    import base64
    audio, done, err = tts_volc._take_line(json.dumps({"code": 0, "data": base64.b64encode(b"abc").decode()}))
    assert audio == b"abc" and not done and not err
    audio, done, err = tts_volc._take_line(json.dumps({"code": 20000000}))
    assert done and not err


def test_foreign_keys_stay_with_their_vendor():
    for name in (
        "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY",
        "DASHSCOPE_API_KEY", "ARK_API_KEY",
    ):
        os.environ.pop(name, None)
    openai = {"api_key": "sk-openai", "base_url": "https://api.openai.com/v1"}
    gemini = {"api_key": "AIza-test", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"}
    ali = {"api_key": "sk-ali", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}
    assert cloud_key.openai_key(openai) == "sk-openai"
    assert cloud_key.openai_key(ali) == ""
    assert cloud_key.ali_key(openai) == ""
    assert cloud_key.gemini_key(gemini) == "AIza-test"
    assert cloud_key.gemini_key(openai) == ""
    assert cloud_key.eleven_key(openai) == ""
    assert cloud_key.volc_speech_key(gemini) == ""
    os.environ["ELEVENLABS_API_KEY"] = "xi-test"
    try:
        assert cloud_key.eleven_key(ali) == "xi-test"
    finally:
        os.environ.pop("ELEVENLABS_API_KEY", None)


def test_foreign_voice_packs_and_bodies():
    import base64
    from app.services import asr_eleven, asr_gemini, asr_openai, tts_eleven, tts_gemini, tts_openai
    assert len(tts_openai.OPENAI_VOICES) == 13
    assert len(tts_gemini.GEMINI_VOICES) == 30
    assert len(tts_eleven.ELEVEN_VOICES) == 52
    assert len({v["id"] for v in tts_eleven.ELEVEN_VOICES}) == 52
    assert any(v["id"] == "marin" for v in tts_openai.OPENAI_VOICES)
    assert any(v["id"] == "21m00Tcm4TlvDq8ikWAM" for v in tts_eleven.ELEVEN_VOICES)
    assert any(v["id"] == "Kore" for v in tts_gemini.GEMINI_VOICES)
    assert default_voice("openai", "zh-CN") == "marin"
    assert default_voice("eleven", "ja") == "21m00Tcm4TlvDq8ikWAM"
    assert default_voice("gemini", "en") == "Kore"
    assert align_voice("openai", "nova", "zh-CN") == "nova"
    assert align_voice("gemini", "Puck", "ja") == "Puck"
    body = tts_openai.request_body("你好", "marin")
    assert body["model"] == "gpt-4o-mini-tts" and body["voice"] == "marin" and body["response_format"] == "mp3"
    assert asr_openai.OPENAI_ASR_MODEL == "gpt-transcribe"
    assert asr_openai.text_of({"text": " 你好 "}) == "你好"
    assert "scribe_v2" == asr_eleven.ELEVEN_ASR_MODEL
    assert "Rachel" not in tts_eleven.speech_url("21m00Tcm4TlvDq8ikWAM")
    assert tts_eleven.speech_url("21m00Tcm4TlvDq8ikWAM").endswith("/stream?output_format=mp3_44100_128")
    gbody = asr_gemini.request_body(b"RIFFxxxx")
    inline = gbody["contents"][0]["parts"][1]["inlineData"]
    assert inline["mimeType"] == "audio/wav"
    assert inline["data"] == base64.b64encode(b"RIFFxxxx").decode("ascii")
    heard = asr_gemini.text_of({"candidates": [{"content": {"parts": [{"text": "在吗"}]}}]})
    assert heard == "在吗"
    pcm = tts_gemini.pcm_of({
        "candidates": [{"content": {"parts": [{
            "inlineData": {"data": base64.b64encode(b"\x01\x00\x02\x00").decode("ascii")},
        }]}}],
    })
    assert pcm == b"\x01\x00\x02\x00"
    line = "data: " + json.dumps({
        "candidates": [{"content": {"parts": [{
            "inlineData": {"data": base64.b64encode(b"\x03\x00").decode("ascii")},
        }]}}],
    })
    assert tts_gemini._pcm_from_sse_line(line) == b"\x03\x00"
