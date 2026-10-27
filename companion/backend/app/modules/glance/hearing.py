"""系统声。台词和歌词从扬声器环回里听，不从画面上认。

听不到、没有环回设备，就当这一眼没有声音。她自己在说的时候不听。
装了 soundcard 才有环回；没装就一直是空的。
"""
from __future__ import annotations

import io
import re
import threading
import time
import wave

_lock = threading.Lock()


class Ear:
    def __init__(self) -> None:
        self._text = ""
        self._at = 0.0
        self._pause_until = 0.0
        self._quiet = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not _can_hear():
            return
        self._stop.clear()
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="glance-ear", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=1.5)

    def set_quiet(self, quiet: bool) -> None:
        with _lock:
            if quiet and not self._quiet:
                self._text = ""
            self._quiet = quiet

    def hush(self, seconds: float) -> None:
        with _lock:
            self._pause_until = max(self._pause_until, time.time() + seconds)
            self._text = ""

    def latest(self) -> str:
        with _lock:
            if self._quiet or time.time() < self._pause_until:
                return ""
            if not self._text or time.time() - self._at > 18:
                return ""
            return self._text

    def once(self, seconds: float = 2.0) -> str:
        got = self.latest()
        if got:
            return got
        if self._blocked():
            return ""
        return self._take(seconds)

    def _blocked(self) -> bool:
        with _lock:
            return self._quiet or time.time() < self._pause_until

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._blocked():
                self._stop.wait(0.4)
                continue
            self._take(3.2)
            self._stop.wait(3.0)

    def _take(self, seconds: float) -> str:
        wav = _record_span(self._stop, seconds)
        if not wav or self._stop.is_set():
            return ""
        try:
            from ...services.asr import transcribe

            text = clean_heard(transcribe(wav))
        except Exception:
            return ""
        if not text:
            return ""
        with _lock:
            self._text = text
            self._at = time.time()
        return text


ear = Ear()


def clean_heard(text: str) -> str:
    raw = " ".join((text or "").split())
    raw = re.sub(r"<\|.*?\|>", "", raw).strip()
    if len(raw) < 2:
        return ""
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", raw):
        return ""
    return raw[:80]


def _can_hear() -> bool:
    try:
        import soundcard  # noqa: F401
    except Exception:
        return False
    return True


def _capture(seconds: float):
    if not _can_hear():
        return None
    try:
        import soundcard as sc

        speaker = sc.default_speaker()
        mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        frames = max(1, int(16000 * seconds))
        return mic.record(samplerate=16000, numframes=frames)
    except Exception:
        return None


def _record(seconds: float) -> bytes | None:
    data = _capture(seconds)
    if data is None:
        return None
    return _wav(data)


def _record_span(stop: threading.Event, seconds: float) -> bytes | None:
    """半秒一段。关掉视觉时不用等这一整段录完。"""
    import numpy as np

    pieces = []
    left = seconds
    while left > 0.05:
        if stop.is_set():
            return None
        step = 0.5 if left > 0.5 else left
        data = _capture(step)
        if data is None:
            return None
        pieces.append(np.asarray(data, dtype=np.float32))
        left -= step
    if stop.is_set() or not pieces:
        return None
    return _wav(np.concatenate(pieces, axis=0))


def _wav(data) -> bytes | None:
    import numpy as np

    samples = np.asarray(data, dtype=np.float32)
    if samples.size == 0:
        return None
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(pcm.tobytes())
    return buf.getvalue()
