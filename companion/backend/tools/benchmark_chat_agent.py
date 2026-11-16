"""Real-provider latency probe using saved settings and an isolated dsh home.

Run from backend: .venv/Scripts/python.exe tools/benchmark_chat_agent.py
Never prints credentials or writes to the user's character/chat records.
"""
from __future__ import annotations

import asyncio
import argparse
import io
import json
import sys
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session
from app.db import engine
from app.services import settings_store, prompt_stack, llm, duplex
from app.services import cloud_key, tts as tts_service, tts_mimo
from app.modules.harness import service
from app.modules.harness.brief import host_brief
from app.locale_pack import set_reply
import httpx
from deepseek_harness.client import HarnessClient


class TimedRuntime(service.Runtime):
    def __init__(self):
        super().__init__()
        self.metrics = {}

    def _ensure_open(self, harness, session_id):
        start = time.perf_counter()
        try:
            return super()._ensure_open(harness, session_id)
        finally:
            self.metrics["runtime_ready_ms"] = round((time.perf_counter() - start) * 1000)

    def _run_turn_locked(self, conf, **kwargs):
        callback = kwargs["on_delta"]
        def on_delta(text):
            self.metrics.setdefault("raw_delta_at", time.perf_counter())
            callback(text)
        kwargs["on_delta"] = on_delta
        return super()._run_turn_locked(conf, **kwargs)


async def mimo_audio_probe(text, conf, started, play_audio=False):
    tts_conf = conf.get("tts") or {}
    llm_conf = settings_store.apply_llm_overlay(dict(conf.get("llm") or {}))
    voice = tts_service.resolve_voice("mimo", str(tts_conf.get("voice") or ""), str(tts_conf.get("voice") or ""))
    stream = tts_mimo.synthesize_pcm(text, voice, cloud_key.mimo_key(llm_conf), "", str(llm_conf.get("base_url") or ""))
    first_ms = None
    pcm = bytearray()
    async for chunk in stream:
        if first_ms is None:
            first_ms = round((time.perf_counter() - started) * 1000)
        pcm.extend(chunk)
    result = {"first_audio_ready_ms": first_ms,
            "tts_complete_ms": round((time.perf_counter() - started) * 1000),
            "audio_seconds": round(len(pcm) / 2 / tts_mimo.SAMPLE_RATE, 3)}
    if play_audio:
        if not pcm or len(pcm) % 2:
            raise RuntimeError("TTS returned empty or malformed PCM")
        import winsound
        wav = io.BytesIO()
        with wave.open(wav, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(tts_mimo.SAMPLE_RATE)
            output.writeframes(pcm)
        result["playback_start_ms"] = round((time.perf_counter() - started) * 1000)
        await asyncio.to_thread(winsound.PlaySound, wav.getvalue(), winsound.SND_MEMORY)
        result["playback_complete_ms"] = round((time.perf_counter() - started) * 1000)
        result["system_playback"] = "completed"
    return result


async def measure(label, source, current, conf=None, with_tts=False, play_audio=False):
    start = time.perf_counter()
    metrics = {}
    current.metrics = metrics
    original_send = httpx.AsyncClient.send
    original_rpc = HarnessClient.request
    def timed_rpc(client, method, params, **kwargs):
        rpc_start = time.perf_counter()
        try:
            return original_rpc(client, method, params, **kwargs)
        finally:
            metrics.setdefault("runtime_rpc", []).append({
                "method": method,
                "start_ms": round((rpc_start - start) * 1000),
                "duration_ms": round((time.perf_counter() - rpc_start) * 1000),
            })
    async def timed_send(client, request, **kwargs):
        request_start = time.perf_counter()
        entry = {"dispatch_ms": round((request_start - start) * 1000), "bytes": len(request.content)}
        try:
            body = json.loads(request.content)
            entry["messages"] = len(body.get("messages") or [])
            entry["system_chars"] = len(json.dumps(body.get("system") or "", ensure_ascii=False))
            entry["tools"] = [tool.get("name") for tool in body.get("tools") or []]
        except (ValueError, TypeError):
            pass
        metrics.setdefault("requests", []).append(entry)
        response = await original_send(client, request, **kwargs)
        entry["headers_ms"] = round((time.perf_counter() - request_start) * 1000)
        return response
    first_text = first_sentence = None
    audio_task = None
    text, errors = [], []
    with patch.object(httpx.AsyncClient, "send", timed_send), patch.object(HarnessClient, "request", timed_rpc):
        async with asyncio.timeout(190):
            async for event in duplex.annotate_stream(source, filler=False, delayed_sec=0):
                elapsed = round((time.perf_counter() - start) * 1000)
                if event.get("type") == "text" and event.get("delta"):
                    if first_text is None:
                        first_text = elapsed
                        print(json.dumps({"progress": label, "first_text_ms": elapsed}, ensure_ascii=False), flush=True)
                    text.append(event["delta"])
                if event.get("type") == "speech" and event.get("text") and first_sentence is None:
                    first_sentence = elapsed
                    if with_tts and conf and (conf.get("tts") or {}).get("engine") == "mimo":
                        audio_task = asyncio.create_task(mimo_audio_probe(event["text"], conf, start, play_audio))
                if event.get("type") == "error":
                    errors.append(str(event.get("message") or event.get("code"))[:400])
    result = {"label": label, "first_text_ms": first_text, "first_tts_unit_ms": first_sentence,
              "total_ms": round((time.perf_counter() - start) * 1000), "reply": "".join(text), "errors": errors}
    if audio_task:
        try:
            result.update(await audio_task)
        except Exception as exc:
            result["tts_error"] = f"{type(exc).__name__}: {exc}"[:300]
    raw_at = metrics.pop("raw_delta_at", None)
    if raw_at is not None:
        metrics["first_raw_delta_ms"] = round((raw_at - start) * 1000)
        metrics["text_gate_ms"] = first_text - metrics["first_raw_delta_ms"] if first_text is not None else None
    result["timings"] = metrics
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsh-only", action="store_true")
    parser.add_argument("--prewarm", action="store_true")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--route", choices=("dsh", "direct", "both"), default="both")
    parser.add_argument("--with-tts", action="store_true")
    parser.add_argument("--play-audio", action="store_true",
                        help="Play the first speech unit through the Windows audio device")
    parser.add_argument("--continue-on-error", action="store_true")
    options = parser.parse_args()
    with Session(engine) as session:
        conf = settings_store.get_all(session)
    # Synthetic input only: do not load the user's character or chat history.
    persona = "你是一个温柔自然的中文聊天伙伴。用一两句简短口语接住对方的话，不要写计划、分析或旁白。"
    name, boundary = "测试伙伴", "strict"
    config = service.harness_llm(conf.get("llm") or {})
    set_reply((conf.get("locale") or {}).get("reply") or "zh-CN")
    print(json.dumps({"model": config.get("model"), "host": urlsplit(config.get("base_url") or "").hostname,
        "thinking": config.get("thinking", "default"), "max_tokens": config.get("max_tokens"),
        "key_configured": bool(config.get("api_key")), "tts_engine": (conf.get("tts") or {}).get("engine")}, ensure_ascii=False), flush=True)
    prompts = [
        "我今天有点累，陪我说两句吧。", "我刚才说我今天怎么样？一句话回答。",
        "给我一个今晚放松的小建议，只说两句话。", "窗外天气看起来不错，想和你聊聊。",
        "如果现在一起喝茶，你会聊什么？", "今天做完了一件拖了很久的事。",
        "用一句轻松的话鼓励我一下。", "你觉得休息十分钟可以做什么？",
        "我有点纠结晚饭吃什么。", "跟我说一句适合睡前听的话。",
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix="real-chat-benchmark-") as folder:
        home = Path(folder)
        current = TimedRuntime()
        with patch.object(service, "home_dir", lambda: home), patch.object(service, "runtime", lambda: current), patch.object(service, "glance_on", lambda: False):
            try:
                if options.prewarm:
                    start = time.perf_counter()
                    await asyncio.to_thread(current.warmup, config)
                    print(json.dumps({"prewarm_ms": round((time.perf_counter() - start) * 1000)}), flush=True)
                routes = (("dsh",) if options.dsh_only or options.route == "dsh" else
                          ("direct_same_model",) if options.route == "direct" else ("dsh", "direct_same_model"))
                for route in routes:
                    history = []
                    for index in range(max(1, options.rounds)):
                        prompt = prompts[index % len(prompts)]
                        messages = prompt_stack.build_messages(persona=persona, char_name=name,
                            motion_groups={}, history=history + [{"role": "user", "content": prompt}],
                            user_text=prompt, mode="user", last_at=None, character_id=-999, boundary=boundary)
                        source = service.stream_reply(config, character_id=-999, user_text=prompt,
                            brief=host_brief(messages), prior=history, timeout=180) if route == "dsh" else llm.stream_chat(config, messages)
                        result = await measure(f"{route}_{index + 1}", source, current, conf,
                                               options.with_tts or options.play_audio, options.play_audio)
                        results.append(result)
                        history += [{"role": "user", "content": prompt}, {"role": "assistant", "content": result["reply"]}]
                        if result["errors"] and not options.continue_on_error:
                            break
            finally:
                current.close()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = Path(__file__).resolve().parents[1] / "data" / f"chat-agent-benchmark-{stamp}.json"
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"results_file": str(output)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
