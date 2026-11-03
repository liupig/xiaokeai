"""长句要在流式解码撕开之前切开。不加载模型。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.tts_qwen import _float_torn, _token_cap, _utterances  # noqa: E402


def test_a_long_chinese_line_stays_inside_the_clean_window():
    line = "我不信这一手，两张少女你也敢跟，枪在我这儿。"
    parts = _utterances(line)
    assert parts
    assert "".join(parts) == line
    assert all(len(part) <= 12 for part in parts)
    assert all(_token_cap(part) <= 36 for part in parts)


def test_english_is_cut_on_words():
    line = "I do not believe this hand, and the gun is still mine tonight friend."
    parts = _utterances(line)
    assert " ".join(parts) == line
    assert all(len(part) <= 48 for part in parts)
    assert all(_token_cap(part) <= 36 for part in parts)


def test_full_scale_tearing_is_not_a_normal_vowel():
    vowel = (np.sin(np.linspace(0, 40, 8000)) * 0.4).astype(np.float32)
    torn = np.zeros(8000, dtype=np.float32)
    torn[::2] = 0.98
    torn[1::2] = -0.98
    assert not _float_torn(vowel)
    assert _float_torn(torn)
