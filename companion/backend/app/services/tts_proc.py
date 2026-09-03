"""Qwen TTS 独立进程：独占 GPU，不和 ASR / FastAPI 抢同一个解释器。"""
from __future__ import annotations

import os
import traceback
from queue import Queue
from threading import Thread


def main(in_q, out_q, cancel_ev) -> None:
    os.environ["COMPANION_TTS_WORKER"] = "1"
    from app.infer_runtime import prepare_worker
    prepare_worker("tts")
    from app.services.tts_qwen import (
        _warmup_inproc,
        _status_inproc,
        synthesize_pcm_sync,
    )

    work: Queue = Queue()
    current = {"job": ""}

    def recv() -> None:
        while True:
            try:
                cmd = in_q.get()
            except (EOFError, OSError, KeyboardInterrupt):
                work.put(("stop",))
                return
            if not cmd or cmd[0] == "stop":
                work.put(("stop",))
                return
            if cmd[0] == "cancel":
                if cmd[1] == current["job"]:
                    cancel_ev.set()
                continue
            work.put(cmd)

    Thread(target=recv, daemon=True, name="tts-recv").start()

    while True:
        cmd = work.get()
        if not cmd or cmd[0] == "stop":
            break
        kind = cmd[0]
        try:
            if kind == "warmup":
                st = _warmup_inproc(cmd[1])
                out_q.put(("ok", "warmup", st))
            elif kind == "status":
                out_q.put(("ok", "status", _status_inproc()))
            elif kind == "synth":
                _, job, text, voice, size, instruct = cmd
                current["job"] = job
                cancel_ev.clear()
                try:
                    for pcm in synthesize_pcm_sync(text, voice, size, instruct, cancel_ev):
                        if cancel_ev.is_set():
                            break
                        out_q.put(("pcm", job, pcm))
                    out_q.put(("done", job, b""))
                except Exception as exc:
                    extra = str(exc)
                    try:
                        import torch
                        if torch.cuda.is_available():
                            free, total = torch.cuda.mem_get_info()
                            extra += (
                                f" (cuda free={free / 1024 ** 2:.0f}MiB / {total / 1024 ** 2:.0f}MiB)"
                            )
                    except Exception:
                        pass
                    out_q.put(("err", job, extra))
                finally:
                    current["job"] = ""
            else:
                continue
        except Exception as exc:
            out_q.put(("err", kind, f"{exc}\n{traceback.format_exc()}"))
