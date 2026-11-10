"""Measure Tera first audio and completion on the configured provider."""
import asyncio
import threading
import time
from app.services import tts_tera


async def main():
    for label in ('cold', 'warm'):
        start = time.perf_counter()
        first = None
        total = 0
        async for chunk in tts_tera.synthesize_pcm('Привет! Рада тебя видеть. Как прошёл твой день?', 'ru_f1', threading.Event()):
            if first is None:
                first = time.perf_counter() - start
            total += len(chunk)
        elapsed = time.perf_counter() - start
        print(f'{label}: first={first:.3f}s total={elapsed:.3f}s audio={total / 2 / tts_tera.SAMPLE_RATE:.3f}s bytes={total}', flush=True)
    for row in tts_tera.VOICES:
        total = 0
        async for chunk in tts_tera.synthesize_pcm('Привет.' if row['lang'] == 'ru' else 'Hello.', row['id'], threading.Event(), row['lang']):
            total += len(chunk)
        print(f"voice={row['id']} bytes={total}", flush=True)
    tts_tera.release()

if __name__ == '__main__':
    asyncio.run(main())
