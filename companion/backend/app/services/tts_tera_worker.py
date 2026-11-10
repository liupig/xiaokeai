"""Isolated Tera GPU worker. stdout is a line-delimited private IPC channel."""
from __future__ import annotations

import base64
import contextlib
import json
import os
import sys
from pathlib import Path


def main():
    channel = sys.stdout
    def send(value):
        channel.write(json.dumps(value) + '\n')
        channel.flush()

    with contextlib.redirect_stdout(sys.stderr):
        try:
            gpu_runtime = Path(os.environ['COMPANION_TERA_GPU_RUNTIME'])
            sys.path.insert(0, str(gpu_runtime))
            import torch  # Loads the CUDA libraries packaged with PyTorch on Windows.
            import onnxruntime as ort
            if 'CUDAExecutionProvider' not in ort.get_available_providers():
                raise RuntimeError('ONNX Runtime CUDA provider is not installed')
            if hasattr(ort, 'preload_dlls'):
                ort.preload_dlls()
            from app.services import tts_tera
            tts_tera._provider = 'CUDAExecutionProvider'
            model = tts_tera._load()
            sessions = (model.text_encoder, model.duration_predictor, model.sampler, model.vocoder)
            if any('CUDAExecutionProvider' not in session.get_providers() for session in sessions):
                raise RuntimeError('TeraTTS failed to initialize CUDA on one or more model components')
        except Exception as exc:
            send({'kind': 'error', 'message': str(exc)})
            return
        send({'kind': 'ready', 'provider': 'CUDAExecutionProvider'})
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if command.get('stop'):
                    break
                text = str(command['text']).replace('<', '').replace('>', '')
                lang = command['language']
                if lang not in ('ru', 'en'):
                    raise ValueError('Unsupported TeraTTS language')
                import numpy as np
                for chunk in tts_tera._runtime.generate_speech_stream(
                    model, f'<{lang}>{text}</{lang}>', command['voice'], chunk_frames=8
                ):
                    pcm = (np.clip(chunk, -1, 1) * 32767).astype('<i2').tobytes()
                    if pcm:
                        send({'kind': 'audio', 'data': base64.b64encode(pcm).decode('ascii')})
                send({'kind': 'end'})
            except Exception as exc:
                send({'kind': 'error', 'message': str(exc)})
                send({'kind': 'end'})


if __name__ == '__main__':
    main()
