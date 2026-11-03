"""Replay archived media facts and separately labelled constructed scene contracts."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.sight import service
from app.modules.glance.media_director import cadence
from app.modules.glance.watch import along_turn
from app.modules.glance.watch import WatchSession
from app.modules.glance.situation import Situation, parse_observation


CASES = [
    ("movie", "vlc.exe", "某部电影", "片名：某部电影\n字幕：你回来就好\n画面：两个人在车站拥抱", True),
    ("series", "vlc.exe", "某剧 第12集", "剧名：某剧 第12集\n字幕：这封信怎么在你手里\n画面：女子举着信封质问面前的人", True),
    ("video", "chrome.exe", "抖音", "标题：搬家的小狗\n画面：小狗拖着比自己还大的垫子走到门口", True),
    ("music", "cloudmusic.exe", "某首歌 - 网易云音乐", "歌名：某首歌\n歌手：甲\n歌词：窗外的雨还没有停\n播放状态：playing", True),
    ("pause", "vlc.exe", "某部电影", "播放状态：paused", False),
    ("search", "chrome.exe", "抖音", "画面：搜索结果页，尚未确认正在播放\n播放状态：unavailable", False),
]


def candidate(brief):
    sit = Situation()
    watch = WatchSession(sit)
    stamp = time.time()
    watch.pulse(stamp)
    obs = parse_observation(brief.handoff, timestamp=stamp)
    obs.channel = brief.slots.get("line_source") or "sight"
    offer = watch.admit(obs, sit.ingest(obs))
    if offer:
        from app.modules.glance.media_director import bind_context
        bind_context(offer, brief.public())
        watch.candidate.summary = offer.summary
    allowed = cadence(brief.kind, elapsed=99, opening=True, talk="normal", playback=brief.slots.get("playback", ""))
    return offer if allowed else None


def eligible(brief):
    return candidate(brief) is not None


async def run(args):
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    fresh = {row["id"]: row for row in json.loads((root / "fresh-vision.json").read_text(encoding="utf-8"))}
    rows = json.loads((root / "records.json").read_text(encoding="utf-8"))
    history = []
    for row in rows:
        service.reset()
        source = fresh.get(row["id"], row)
        text = source.get("result", "")
        # Legacy forced-stage answers provide no content evidence.
        if text.strip() in {"在刷", "在看", "直播", "playing"}:
            text = ""
        brief = service.commit("chrome.exe", "抖音", "抖音", text)
        offer = candidate(brief)
        history.append({"id": row["id"], "source": "fresh-image" if row["id"] in fresh else "archived-model-text",
                        "input": text, "handoff": brief.handoff, "summary": offer.summary if offer else "", "company": brief.company,
                        "eligible": offer is not None})
    (root / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    checks = []
    for name, process, title, text, expected in CASES:
        service.reset()
        brief = service.commit(process, title, title, text)
        offer = candidate(brief)
        actual = offer is not None
        assert actual == expected, (name, brief)
        checks.append({"id": name, "source": "constructed-contract", "summary": offer.summary if offer else brief.handoff,
                       "company": brief.company, "scene": brief.kind, "eligible": actual})
    (root / "contracts.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.live:
        from sqlmodel import Session, select
        from app.db import engine
        from app.models import Character
        from app.services.settings_store import get_all
        from app.services.llm import SYSTEM_PROTOCOL
        from app.modules.glance.game_director import grounded_reply

        with Session(engine) as db:
            config = get_all(db)
            character = db.exec(select(Character).order_by(Character.id)).first()
            persona = character.persona if character else "你是小可爱。"
        replies = []
        candidates = [r for r in checks if r["eligible"]]
        candidates += [{"id": r["id"], "source": r["source"], "summary": r["summary"], "company": r["company"], "scene": "video"}
                       for r in history if r["source"] == "fresh-image" and r["eligible"]]
        for row in candidates:
            from app.modules.sight.service import bound_speech
            instruction = bound_speech(along_turn(), line=row["summary"], rule=row["company"])
            messages = [{"role": "system", "content": persona + "\n" + SYSTEM_PROTOCOL + "\n" + row["summary"] + "\n" + row["company"]},
                        {"role": "user", "content": instruction}]
            reply = await grounded_reply(config["llm"], messages, evidence=row["summary"], topic=row["id"], scene=row["scene"])
            replies.append({**row, "reply": reply["text"], "action": reply["action"], "attempts": reply["attempts"], "playback": "not-tested"})
            (root / "real-dialogues.json").write_text(json.dumps(replies, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(replies[-1], ensure_ascii=False), flush=True)
    print(json.dumps({"history": len(history), "fresh_images": len(fresh), "eligible": sum(r["eligible"] for r in history), "contracts": len(checks)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/media-eval"))
    parser.add_argument("--live", action="store_true")
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run(parser.parse_args()))
