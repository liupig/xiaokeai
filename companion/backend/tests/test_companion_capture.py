"""Exercise the actual eye service's frame contract without loading GPU weights."""
import importlib.util
from pathlib import Path
import sys

from PIL import Image
import pytest


@pytest.fixture
def eye():
    path = Path(__file__).resolve().parents[3] / "minicpm-o-demo" / "v47" / "engine.py"
    spec = importlib.util.spec_from_file_location("_capture_contract_engine", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_structured_prompt_does_not_silently_reduce_requested_frames(eye, monkeypatch):
    images = [Image.new("RGB", (160, 100), (80+i, 100, 120)) for i in range(4)]
    frames = [(100+i, image, eye._sig(image), i+1) for i, image in enumerate(images)]
    monkeypatch.setattr(eye, "_target_window", lambda hwnd: frames)
    monkeypatch.setattr(eye, "_dump_reel", lambda images: None)
    monkeypatch.setattr(eye, "_game_text", lambda image: "")
    found = eye.glance_once(infer=False, window_hwnd=123, prompt="英雄联盟", detail=True, frames=4)
    assert found["ok"]
    assert found["frames"] == 4
    assert len(found["images"]) == 4
    assert found["observed_at"] == 103


def test_unreadable_target_does_not_fall_back_to_another_window(eye, monkeypatch):
    monkeypatch.setattr(eye, "_target_window", lambda hwnd: [])
    monkeypatch.setattr(eye, "_ensure_reel", lambda index: pytest.fail("must not capture the desktop instead"))
    found = eye.glance_once(infer=False, window_hwnd=123, prompt="英雄联盟")
    assert not found["ok"]
    assert "目标窗口" in found["message"]


def test_ocr_starts_before_gpu_and_is_scoped_to_that_frame(eye, monkeypatch):
    import threading
    from types import SimpleNamespace
    entered = threading.Event()
    finish = threading.Event()
    def read(frame):
        entered.set()
        assert finish.wait(2)
        return [{"text": str(frame.getpixel((0, 0)))}]
    monkeypatch.setattr(eye, "_get_screen_reader", lambda: SimpleNamespace(read=read))
    image = Image.new("RGB", (10, 10), "red")
    job = eye._start_ocr(image)
    try:
        assert entered.wait(1)
        assert eye._start_ocr(Image.new("RGB", (10, 10), "blue")) is None
        rows, status = eye._finish_ocr(job)
        assert rows == [] and status == "pending-skipped"
    finally:
        finish.set()
        job.result(timeout=2)
    assert eye._finish_ocr(None)[0] == []
    assert eye._finish_ocr(job)[0] == [{"text": "(255, 0, 0)"}]


def test_ocr_cache_requires_exact_pixels_and_does_not_retain_failure(monkeypatch):
    monkeypatch.setenv("XIAOKE_OCR_ENGINE", "windows")
    from collections import OrderedDict
    from app.modules.sight import screen_text
    monkeypatch.setattr(screen_text, "_ocr_cache", OrderedDict())
    calls = []
    def native(frame):
        calls.append(1)
        return [{"text": "原字"}]
    monkeypatch.setattr(screen_text, "_read_native", native)
    image = Image.new("RGB", (10, 10), "red")
    first = screen_text.read(image)
    first[0]["text"] = "modified"
    assert screen_text.read(image)[0]["text"] == "原字"
    assert len(calls) == 1
    image.putpixel((0, 0), (254, 0, 0))
    screen_text.read(image)
    assert len(calls) == 2
    from types import SimpleNamespace
    expired_time = screen_text.time.monotonic() + 31
    monkeypatch.setattr(screen_text, "time", SimpleNamespace(monotonic=lambda: expired_time))
    screen_text.read(image)
    assert len(calls) == 3
    monkeypatch.setattr(screen_text, "_read_native", lambda frame: [])
    blue = Image.new("RGB", (10, 10), "blue")
    assert screen_text.read(blue) == []
    monkeypatch.setattr(screen_text, "_read_native", native)
    assert screen_text.read(blue)


def test_live_glance_overlaps_native_ocr_with_model_generation(eye, monkeypatch):
    import threading
    import time
    from types import SimpleNamespace
    entered = threading.Event()
    release = threading.Event()
    reads = []
    def read(frame):
        reads.append(frame.getpixel((0, 0)))
        entered.set()
        assert release.wait(2)
        return [{"text": "原字"}]
    def ask(*args, **kwargs):
        assert entered.wait(1), "OCR must already be running during model generation"
        release.set()
        return "画面：角色正在移动"
    reader = SimpleNamespace(read=read, verify=lambda text, lines: text,
                             facts=lambda lines, **kwargs: "原文：" + lines[0]["text"] if lines else "")
    image = Image.new("RGB", (160, 100), "red")
    monkeypatch.setattr(eye, "_get_screen_reader", lambda: reader)
    monkeypatch.setattr(eye, "_screen_text_reader", reader)
    monkeypatch.setattr(eye, "_target_window", lambda hwnd: [(time.time(), image, eye._sig(image), 1)])
    monkeypatch.setattr(eye, "_target_valid", True)
    monkeypatch.setattr(eye, "load", lambda: None)
    monkeypatch.setattr(eye, "_ask", ask)
    monkeypatch.setattr(eye, "_dump_reel", lambda images: None)
    found = eye.glance_once(window_hwnd=123, prompt="英雄联盟", detail=True, frames=1)
    assert found["profile"]["ocr_status"] == "ready"
    assert "原文：原字" in found["text"]
    assert reads == [(255, 0, 0)]
