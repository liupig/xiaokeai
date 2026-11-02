from collections import OrderedDict
from types import SimpleNamespace

import pytest
from PIL import Image

from app.modules.sight import screen_text, rapid_text


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("XIAOKE_OCR_ENGINE", "rapidocr")
    monkeypatch.setattr(screen_text, "_ocr_cache", OrderedDict())
    monkeypatch.setattr(screen_text, "_rapid_retry_at", 0)


def test_default_reader_uses_rapidocr_and_does_not_fallback_on_valid_empty(monkeypatch):
    monkeypatch.setattr(screen_text, "_rapid_reader", SimpleNamespace(read=lambda image: []))
    monkeypatch.setattr(screen_text, "_read_native", lambda image: pytest.fail("Blank frames are not backend failures"))
    assert screen_text.read(Image.new("RGB", (10, 10))) == []


def test_initialization_failure_falls_back_and_backs_off(monkeypatch):
    calls = []
    def broken(image):
        calls.append(1)
        raise RuntimeError("missing model")
    monkeypatch.setattr(screen_text, "_rapid_reader", SimpleNamespace(read=broken))
    monkeypatch.setattr(screen_text, "_read_native", lambda image: [{"text": "fallback"}])
    image = Image.new("RGB", (10, 10))
    assert screen_text._read_backend(image)[0]["text"] == "fallback"
    assert screen_text._read_backend(image)[0]["text"] == "fallback"
    assert len(calls) == 1


def test_korean_rereads_only_uncertain_regions_and_keeps_coordinates(monkeypatch):
    import numpy as np
    result = SimpleNamespace(boxes=np.array([[[10, 10], [100, 10], [100, 30], [10, 30]],
                                            [[10, 40], [100, 40], [100, 60], [10, 60]]]),
                             txts=["继续游戏", "H .E."], scores=[.99, .6])
    crops = []
    def recognize(values):
        crops.extend(values)
        return SimpleNamespace(txts=["배가 떠나요"], scores=[.99])
    monkeypatch.setattr(rapid_text, "_engine", lambda image: result)
    monkeypatch.setattr(rapid_text, "_korean", SimpleNamespace(recognize_txt=recognize))
    rows = rapid_text.read(Image.new("RGB", (120, 80)))
    assert len(crops) == 1
    assert [r["text"] for r in rows] == ["继续游戏", "배가 떠나요"]
    assert rows[1]["language"] == "ko"
    assert rows[1]["words"][0]["y"] == 40


def test_split_respawn_number_must_be_next_to_label():
    rows = [{"text": "返回于", "words": [{"x": 100, "y": 100, "width": 40, "height": 12}]},
            {"text": "30", "words": [{"x": 110, "y": 120, "width": 20, "height": 16}]},
            {"text": "999", "words": [{"x": 600, "y": 120, "width": 20, "height": 16}]}]
    assert "返回于 30" in screen_text.facts(rows)
    assert "返回于 999" not in screen_text.facts(rows)


def test_multiple_ocr_lines_preserve_end_button_before_respawn(monkeypatch, tmp_path):
    from app.modules.sight import service
    monkeypatch.setenv("SIGHT_HOME", str(tmp_path))
    service.reload()
    service.reset()
    source = ("League of Legends.exe", "League of Legends", "League of Legends")
    service.commit(*source, "画面：局内HUD可见")
    brief = service.commit(*source, "原文：WB退出了游戏\n原文：继续游戏\n原文：返回于 30")
    assert brief.phase == "score"
    assert "这局结束了" in brief.handoff
    assert "返回于 30" not in brief.handoff
    service.reset()
