"""SenseVoice 独立进程：只跑 CPU 识别，不加载 PyTorch / Qwen。"""
from __future__ import annotations

import os
import traceback


def main(in_q, out_q) -> None:
    os.environ["COMPANION_ASR_WORKER"] = "1"
    from app.infer_runtime import prepare_worker
    prepare_worker("asr")
    try:
        from app.services.asr import _get_recognizer, _transcribe_local
        _get_recognizer()
        out_q.put(("ready", "", ""))
    except Exception as exc:
        out_q.put(("boot-err", "", f"{exc}\n{traceback.format_exc()}"))
        return
    while True:
        try:
            cmd = in_q.get()
        except (EOFError, OSError, KeyboardInterrupt):
            break
        if not cmd or cmd[0] == "stop":
            break
        if cmd[0] != "transcribe":
            continue
        _, job_id, wav = cmd
        try:
            text = _transcribe_local(wav)
            out_q.put(("ok", job_id, text))
        except Exception as exc:
            out_q.put(("err", job_id, str(exc)))
