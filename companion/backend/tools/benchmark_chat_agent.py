"""Real-provider latency probe using saved settings and an isolated dsh home.

Run from backend: .venv/Scripts/python.exe tools/benchmark_chat_agent.py
Never prints credentials or writes to the user's character/chat records.
"""
from __future__ import annotations

import asyncio
import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session
from app.db import engine
from app.services import settings_store, prompt_stack, llm, duplex
from app.modules.harness import service
from app.modules.harness.brief import host_brief
from app.locale_pack import set_reply
import httpx


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


async def measure(label, source, current):
    start = time.perf_counter()
    metrics = {}
    current.metrics = metrics
    original_send = httpx.AsyncClient.send
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
    text, errors = [], []
    with patch.object(httpx.AsyncClient, "send", timed_send):
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
                if event.get("type") == "error":
                    errors.append(str(event.get("message") or event.get("code"))[:400])
    result = {"label": label, "first_text_ms": first_text, "first_tts_unit_ms": first_sentence,
              "total_ms": round((time.perf_counter() - start) * 1000), "reply": "".join(text), "errors": errors}
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
    prompts = ["我今天有点累，陪我说两句吧。", "我刚才说我今天怎么样？一句话回答。", "那你给我一个今晚放松的小建议，只说两句话。"]
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
                for route in (("dsh",) if options.dsh_only else ("dsh", "direct_same_model")):
                    history = []
                    for index, prompt in enumerate(prompts):
                        messages = prompt_stack.build_messages(persona=persona, char_name=name,
                            motion_groups={}, history=history + [{"role": "user", "content": prompt}],
                            user_text=prompt, mode="user", last_at=None, character_id=-999, boundary=boundary)
                        source = service.stream_reply(config, character_id=-999, user_text=prompt,
                            brief=host_brief(messages), prior=history, timeout=180) if route == "dsh" else llm.stream_chat(config, messages)
                        result = await measure(f"{route}_{index + 1}", source, current)
                        results.append(result)
                        history += [{"role": "user", "content": prompt}, {"role": "assistant", "content": result["reply"]}]
                        if result["errors"]:
                            break
            finally:
                current.close()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = Path(__file__).resolve().parents[1] / "data" / f"chat-agent-benchmark-{stamp}.json"
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"results_file": str(output)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
