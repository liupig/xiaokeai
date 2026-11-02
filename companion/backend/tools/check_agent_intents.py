"""Real-model semantic action probes. Never execute returned game/visual actions."""
from __future__ import annotations

import asyncio
import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session
from app.db import engine
from app.services import settings_store
from app.modules.harness import service

CASES = [
    ("今天有点烦，来把大乱斗吧。", {"play"}, []),
    ("帮我把联盟开起来呗。", {"play"}, []),
    ("我已经在打LOL了，你帮我盯着这局。", {"glance"}, []),
    ("瞅瞅我屏幕上这个报错。", {"glance"}, []),
    ("帮我看一下今天金价。", {"lookup"}, []),
    ("一起看看最近有什么新闻。", {"lookup"}, []),
    ("看一下明天天气，地点是北京。", {"lookup"}, []),
    ("英雄联盟真好玩。", set(), []),
    ("别打开英雄联盟，我就随便聊聊。", set(), []),
    ("把眼睛关掉，我不想让你看了。", {"glance"}, []),
    ("我想开一局LOL，你陪我打。", {"play", "glance"}, []),
    ("行，帮我开吧。", {"play"}, [{"role": "user", "content": "我准备玩英雄联盟。"}, {"role": "assistant", "content": "要我帮你开一把吗？"}]),
    ("这个网页上的金价你能看清吗？", {"glance"}, []),
    ("你看一下。", set(), []),
    ("看看英雄联盟最新版本的改动。", {"lookup"}, []),
]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="", help="Comma-separated one-based case numbers")
    args = parser.parse_args()
    selected = {int(value) for value in args.cases.split(",") if value.strip()}
    with Session(engine) as session:
        conf = settings_store.get_all(session)
    config = service.harness_llm(conf.get("llm") or {})
    results = []
    with tempfile.TemporaryDirectory(prefix="semantic-agent-probe-") as folder:
        home = Path(folder)
        current = service.Runtime()
        with patch.object(service, "home_dir", lambda: home), patch.object(service, "runtime", lambda: current), patch.object(service, "visual_available", lambda: True), patch.object(service, "glance_on", lambda: False):
            try:
                await asyncio.to_thread(current.warmup, config)
                for index, (text, expected, prior) in enumerate(CASES):
                    if selected and index + 1 not in selected:
                        continue
                    events = [event async for event in service.stream_reply(config,
                        character_id=-(1000 + index), user_text=text,
                        brief="【稳定身份】\n你是自然的中文陪伴聊天伙伴。\n\n【动态现场】\n【宿主能力】游戏启动可用；视觉环境可按需启动，尚未看见屏幕。用户没有提供所在地时应询问，不能猜。",
                        prior=prior, timeout=90)]
                    actions = [event for event in events if event.get("type") in {"play", "glance", "lookup"}]
                    actual = {event["type"] for event in actions}
                    passed = actual == expected and not any(event["type"] == "error" for event in events)
                    if "关掉" in text:
                        passed = passed and any(event.get("value") == "关闭" for event in actions)
                    if "帮我盯着" in text or "你陪我打" in text:
                        passed = passed and any(str(event.get("value") or "").startswith("陪看") for event in actions if event["type"] == "glance")
                    result = {"text": text, "expected": sorted(expected), "actions": actions, "passed": passed,
                              "reply": "".join(event.get("delta", "") for event in events if event["type"] == "text"),
                              "errors": [event for event in events if event["type"] == "error"]}
                    results.append(result)
                    print(json.dumps(result, ensure_ascii=True), flush=True)
            finally:
                current.close()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = Path(__file__).resolve().parents[1] / "data" / f"semantic-agent-probe-{stamp}.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": sum(row["passed"] for row in results), "total": len(results), "file": str(output)}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
