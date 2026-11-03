"""One bounded CPU OCR sampler, independent of visual-model generation."""
from __future__ import annotations

import threading
from collections import deque


class SubtitleSampler:
    def __init__(self, interval: float = 1.5):
        self.interval = interval
        self._condition = threading.Condition()
        self._source = ""
        self._epoch = 0
        self._reader = None
        self._rows = deque(maxlen=8)
        self._thread = None

    def configure(self, source: str, reader) -> None:
        with self._condition:
            if source != self._source:
                self._source = source
                self._epoch += 1
                self._rows.clear()
            self._reader = reader
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="media-subtitles", daemon=True)
                self._thread.start()
            self._condition.notify_all()

    def reset(self) -> None:
        with self._condition:
            self._source = ""
            self._reader = None
            self._epoch += 1
            self._rows.clear()
            self._condition.notify_all()

    def drain(self, source: str) -> list[dict]:
        with self._condition:
            if source != self._source:
                return []
            rows = list(self._rows)
            self._rows.clear()
            return rows

    def sample(self) -> None:
        with self._condition:
            epoch, reader = self._epoch, self._reader
        if reader is None:
            return
        try:
            result = reader()
        except Exception:
            return
        with self._condition:
            if epoch == self._epoch and self._reader is not None and result.get("ok"):
                self._rows.append(result)

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._reader is not None)
                epoch = self._epoch
            self.sample()
            with self._condition:
                # Refreshing a callback is not a reason to sample again early.
                self._condition.wait_for(lambda: epoch != self._epoch, timeout=self.interval)


subtitles = SubtitleSampler()
