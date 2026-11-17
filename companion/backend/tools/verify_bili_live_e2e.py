"""用公开房间的真实匿名弹幕验证直播主持链路；不发送弹幕，不伪造真实音频证明。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session

from app.db import engine
from app.modules.live.bili.web import WebLiveSession
from app.modules.live.config import normalize
from app.modules.live.host import LiveHost
from app.services import settings_store


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--room", required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with Session(engine) as db:
        settings = settings_store.get_all(db)
    llm = dict(settings.get("llm") or {})
    if not llm.get("api_key"):
        raise SystemExit("当前没有可用于真实模型验证的对话 Key")
    cfg = normalize(settings.get("live"))
    cfg["compliance"]["strict"] = False  # 只改本次内存配置，不写回用户设置。
    cfg["features"].update({"idle": False, "rundown": False, "rehearsal": False, "reply": True})
    cfg["pace"].update({"batch_sec": 1, "batch_size": 3, "user_cooldown_sec": 1, "idle_sec": 600})
    cfg["budget"].update({
        "fallback_base_url": llm.get("base_url") or "",
        "fallback_api_key": llm.get("api_key") or "",
        "fallback_model": llm.get("model") or "",
    })

    host = LiveHost()
    host.use_overrides(cfg, name="晓可", persona="自然、简短地回应观众，不评价主播，不发送任何平台消息。")
    statuses: list[dict] = []
    source = WebLiveSession(args.room, "", host.ingest, statuses.append)
    report: dict = {
        "room": args.room,
        "anonymous": True,
        "read_only": True,
        "audio_verified": False,
        "playback_receipt": "simulated_display_ack",
    }
    try:
        if not host.go_on(0)["ok"]:
            raise RuntimeError("主持开播失败")
        source.start()
        deadline = time.time() + max(10, args.seconds)
        while time.time() < deadline:
            snap = host.snapshot()
            turn = snap.get("turn")
            if turn and turn.get("sources"):
                claimed = host.claim(turn["id"], "local-e2e")
                acked = host.ack(turn["id"], "displayed", "local-e2e")
                report.update({
                    "ok": bool(claimed and acked and snap["budget"]["calls"] >= 1),
                    "source_statuses": statuses,
                    "received_events": len(snap["events"]),
                    "selected_sources": turn["sources"],
                    "generated_reply": turn["text"],
                    "model": {"name": llm.get("model"), "calls": snap["budget"]["calls"],
                              "tokens": snap["budget"]["tokens"], "failures": snap["budget"]["failures"]},
                    "processing": snap["processing"],
                    "playback_claimed": claimed,
                    "playback_acknowledged": acked,
                })
                break
            time.sleep(0.25)
        else:
            snap = host.snapshot()
            report.update({"ok": False, "error": "时限内没有生成真实弹幕回应",
                           "source_statuses": statuses, "received_events": len(snap["events"]),
                           "processing": snap["processing"], "health": snap["health"]})
    finally:
        source.stop()
        host.shutdown()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
