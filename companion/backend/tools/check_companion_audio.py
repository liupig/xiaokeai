"""Real configured TTS -> WAV validation -> optional Windows playback -> ack API."""
from __future__ import annotations

import argparse
import asyncio
from array import array
import json
import math
from pathlib import Path
import sys
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(args):
    from sqlmodel import Session
    from app.db import engine
    from app.services.settings_store import get_all
    from app.services import cloud_key, tts, tts_mimo

    with Session(engine) as database:
        config = get_all(database)
    if config["tts"].get("engine") != "mimo":
        raise RuntimeError("This check expects the currently configured MiMo engine; no fallback voice is selected.")
    voice = tts.resolve_voice("mimo", "", config["tts"].get("voice") or "")
    dialogues = json.loads(args.dialogues.read_text(encoding="utf-8"))
    chosen = next((r for r in dialogues if r.get("reply") and (r.get("id") == args.record_id if args.record_id else r.get("scene") == args.scene if args.scene else "乐芙兰正在进这局" in r.get("summary", ""))), None)
    if chosen is None:
        raise RuntimeError("No validated real model reply matches the requested scene.")
    chunks = []
    async for chunk in tts_mimo.synthesize_pcm(chosen["reply"], voice,
            cloud_key.mimo_key(config["llm"]), "relaxed", config["llm"].get("base_url") or ""):
        chunks.append(chunk)
    pcm = b"".join(chunks)
    if not pcm or len(pcm) % 2:
        raise RuntimeError("Empty or malformed PCM")
    samples = array("h", pcm)
    rms = math.sqrt(sum(int(x) ** 2 for x in samples) / len(samples))
    if rms <= 1:
        raise RuntimeError("TTS produced silent audio")
    output = args.dialogues.with_name("companion-sample.wav")
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(tts_mimo.SAMPLE_RATE)
        wav.writeframes(pcm)
    report = {"text": chosen["reply"], "engine": "mimo", "voice": voice, "audio": str(output.resolve()),
              "duration_sec": len(samples) / tts_mimo.SAMPLE_RATE, "rms": rms,
              "system_playback": "not-tested", "browser_playback": "not-tested"}
    if args.play:
        import winsound

        winsound.PlaySound(str(output.resolve()), winsound.SND_FILENAME)
        report["system_playback"] = "completed"
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.modules.glance import along
        from app.modules.glance.router import router
        from app.modules.glance.situation import Offer

        along._state = along._State(on=True, character_id=1)
        with along._lock:
            along._enqueue(Offer(chosen.get("scene", "game"), "league" if not args.scene else args.scene, chosen["id"], time.time(), 1, chosen["summary"]), "")
        along.generated(chosen["reply"])
        assert not along.live.speeches
        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).post("/api/modules/glance/along/ack",
                                      json={"seq": along.snapshot()["seq"], "status": "completed"})
        assert response.status_code == 200
        assert along.live.speeches[-1] == chosen["reply"]
        report["ack_api"] = "completed"
    args.dialogues.with_name("audio-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogues", type=Path, default=Path("data/companion-eval/real-dialogues.json"))
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--scene", choices=["movie", "video", "music"])
    parser.add_argument("--record-id")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
