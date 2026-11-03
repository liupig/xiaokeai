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
import queue
from collections import deque

_lock = threading.Lock()


class Ear:
    def __init__(self) -> None:
        self._text = ""
        self._at = 0.0
        self._pause_until = 0.0
        self._quiet = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._source = ""
        self._generation = 0
        self._decode_thread: threading.Thread | None = None
        self._pending: queue.Queue = queue.Queue(maxsize=2)
        self._segments: deque = deque(maxlen=8)
        self._dropped = 0
        self._status = "idle"

    def bind(self, source: str) -> None:
        with _lock:
            if source != self._source:
                self._source = source
                self._generation += 1
                self._text = ""
                self._at = 0
                self._segments.clear()

    def clear(self) -> None:
        with _lock:
            self._generation += 1
            self._text = ""
            self._at = 0
            self._segments.clear()

    def start(self) -> None:
        if not _can_hear():
            return
        self._stop.clear()
        if self._thread is not None and self._thread.is_alive():
            return
        if self._decode_thread is None or not self._decode_thread.is_alive():
            self._decode_thread = threading.Thread(target=self._decode_run, name="glance-ear-asr", daemon=True)
            self._decode_thread.start()
        self._thread = threading.Thread(target=self._run, name="glance-ear", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with _lock:
            self._generation += 1
            self._text = ""
            self._segments.clear()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=1.5)
        decoder = self._decode_thread
        if decoder is not None and decoder is not threading.current_thread() and decoder.is_alive():
            decoder.join(timeout=1.5)

    def set_quiet(self, quiet: bool) -> None:
        with _lock:
            if quiet and not self._quiet:
                self._text = ""
                self._generation += 1
                self._segments.clear()
            self._quiet = quiet

    def hush(self, seconds: float) -> None:
        with _lock:
            self._pause_until = max(self._pause_until, time.time() + seconds)
            self._text = ""
            self._generation += 1
            self._segments.clear()

    def latest(self) -> str:
        with _lock:
            if self._quiet or time.time() < self._pause_until:
                return ""
            if not self._text or time.time() - self._at > 8:
                return ""
            return self._text

    def once(self, seconds: float = 2.0) -> str:
        got = self.latest()
        if got:
            return got
        if self._blocked():
            return ""
        if self._thread is not None and self._thread.is_alive():
            return ""
        return self._take(seconds)

    def segments(self) -> list[dict]:
        with _lock:
            if self._quiet or time.time() < self._pause_until:
                return []
            return [dict(row) for row in self._segments if time.time() - row["end"] <= 24]

    def segment(self, text: str) -> dict | None:
        return next((row for row in reversed(self.segments()) if row["text"] == text), None)

    def diagnostics(self) -> dict:
        with _lock:
            return {"status": self._status, "queued": self._pending.qsize(), "dropped": self._dropped}

    def _blocked(self) -> bool:
        with _lock:
            return self._quiet or time.time() < self._pause_until

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._blocked():
                self._stop.wait(0.4)
                continue
            with _lock:
                generation = self._generation
            start = time.time()
            wav = _record_span(self._stop, 3.2)
            end = time.time()
            if not wav:
                with _lock:
                    self._status = "silent_or_unavailable"
                self._stop.wait(.3)
                continue
            self._enqueue((wav, start, end, generation))

    def _enqueue(self, packet) -> None:
        try:
            self._pending.put_nowait(packet)
        except queue.Full:
            try:
                self._pending.get_nowait()
            except queue.Empty:
                pass
            with _lock:
                self._dropped += 1
            try:
                self._pending.put_nowait(packet)
            except queue.Full:
                pass

    def _decode_run(self) -> None:
        while not self._stop.is_set():
            try:
                packet = self._pending.get(timeout=.2)
            except queue.Empty:
                continue
            self._decode(*packet)

    def _take(self, seconds: float) -> str:
        with _lock:
            generation = self._generation
        start = time.time()
        wav = _record_span(self._stop, seconds)
        end = time.time()
        if not wav or self._stop.is_set():
            return ""
        return self._decode(wav, start, end, generation)

    def _decode(self, wav: bytes, start: float, end: float, generation: int) -> str:
        with _lock:
            if generation != self._generation or self._stop.is_set() or self._quiet or time.time() < self._pause_until:
                return ""
        try:
            from ...services.asr import transcribe

            text = clean_heard(transcribe(wav))
        except Exception:
            with _lock:
                self._status = "asr_failed"
            return ""
        if not text:
            with _lock:
                self._status = "no_transcript"
            return ""
        with _lock:
            if generation != self._generation or self._stop.is_set() or self._quiet or time.time() < self._pause_until or time.time() - end > 24:
                return ""
            self._text = text
            self._at = end
            self._status = "recognized"
            self._segments.append({"text": text, "start": start, "end": end, "source": self._source})
        return text


ear = Ear()


def clean_heard(text: str) -> str:
    raw = " ".join((text or "").split())
    raw = re.sub(r"<\|.*?\|>", "", raw).strip()
    if raw.casefold().strip(".!?。！？，, ") in {"the", "a", "an"}:
        return ""
    if len(raw) < 2:
        return ""
    if not re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7afA-Za-z0-9]", raw):
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

    if not _can_hear():
        return None
    pieces = []
    left = seconds
    try:
        import soundcard as sc
        speaker = sc.default_speaker()
        mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        # Keep one loopback stream open for the whole span. Reopening the
        # device every half second used to punch holes into the dialogue.
        with mic.recorder(samplerate=16000) as recorder:
            while left > 0.05:
                if stop.is_set():
                    return None
                step = min(.5, left)
                data = recorder.record(numframes=max(1, int(16000 * step)))
                pieces.append(np.asarray(data, dtype=np.float32))
                left -= step
    except Exception:
        return None
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
    if float(np.sqrt(np.mean(samples ** 2))) < .001:
        return None
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(pcm.tobytes())
    return buf.getvalue()
