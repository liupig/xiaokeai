"""Replay real lab records through production state, event and dialogue gates.

Fresh vision results can replace archived model text by id. This never modifies
the original archive or pretends an offline audio acknowledgement was playback.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.sight import service, session
from app.modules.sight.league import ttl, observation_timing
from app.modules.glance.game_director import cadence, direction
from app.modules.glance.situation import Situation, parse_observation
from app.modules.glance.watch import WatchSession, along_turn, hollow_company, parse_reaction

GAME = ("League of Legends.exe", "League of Legends", "League of Legends")
CLIENT = ("LeagueClientUx.exe", "League of Legends", "League of Legends")


def source(row, previous):
    if row.get("source_process"):
        return (row["source_process"], row.get("source_title", ""), row.get("source_window", "")), "recorded-window"
    text = row.get("result") or ""
    fields = dict(line.split("：", 1) for line in text.splitlines() if "：" in line)
    if fields.get("界面"):
        app = fields["界面"].strip().lower()
        if "leagueclient" in app:
            return CLIENT, "recorded-window"
        if "league" in app:
            return GAME, "recorded-window"
        return (app + ".exe", fields.get("标题", ""), fields.get("窗口", "")), "recorded-window"
    prompt = row.get("prompt") or ""
    if "陪看记录" in text:
        return ("chrome.exe", "陪看记录", "陪看记录"), "recorded-screen"
    if any(x in prompt for x in ("阵亡", "左边商店", "只能写一个：对线", "只能写一个：进入对局")):
        return GAME, "inferred-from-old-prompt"
    if any(x in prompt for x in ("组队、排队、选英雄", "只能写一个：大厅", "只能写一个：排队", "只能写一个：选英雄")):
        return CLIENT, "inferred-from-old-prompt"
    if "League of Legends" in text or any(x in text for x in ("小兵", "泉水", "团战", "胜利", "返回于")):
        return GAME, "inferred-from-old-description"
    return previous, "carried-window-not-recorded"


def replay(rows, fresh):
    service.reset()
    sit = Situation()
    live = WatchSession(sit)
    previous = ("", "", "")
    last_time = 0.0
    last_offer = -1e9
    last_phase = ""
    last_hero = ""
    visual_phase, episode, announced_episode = "", 0, -1
    result = []
    for row in rows:
        stamp = datetime.strptime(row["at"], "%Y-%m-%d %H:%M:%S").timestamp()
        if row.get("id", "").startswith("g"):
            try:
                stamp = datetime.strptime(row["id"][1:18], "%Y%m%d%H%M%S%f").timestamp()
            except ValueError:
                pass
        if stamp - last_time > 120:
            service.reset()
            sit.reset()
            live.reset()
            last_phase = ""
            last_hero = ""
            visual_phase, episode, announced_episode = "", 0, -1
            last_offer = -1e9
        last_time = stamp
        previous, certainty = source(row, previous)
        replacement = fresh.get(row["id"])
        text = (replacement or row).get("result") or ""
        elapsed = float((replacement or row).get("ms") or 0) / 1000
        captured = stamp - elapsed if replacement else float(row.get("observed_at") or stamp - elapsed)
        capture_age = max(0, stamp - captured)
        current = service.current()
        item = {"id": row["id"], "at": row["at"], "mode": "fresh-vision" if replacement else "saved-text",
                "window_source": certainty, "inference_ms": round(elapsed * 1000), "status": "silent"}
        if not (replacement or row).get("ok", True):
            result.append({**item, "status": "vision-error"})
            continue
        if current.sub == "league":
            timing = observation_timing(current.phase, text, capture_age)
            if capture_age > float(timing["freshness_limit"]):
                result.append({**item, **timing, "status": "stale"})
                continue
        with patch.object(session, "time", SimpleNamespace(time=lambda: stamp)):
            brief = service.commit(*previous, text)
        item.update(phase=brief.phase, hero=brief.slots.get("hero", ""), handoff=brief.handoff)
        if brief.phase != visual_phase:
            visual_phase = brief.phase
            episode += 1
        if not brief.active or not brief.handoff:
            result.append(item)
            continue
        obs = parse_observation(brief.handoff, timestamp=captured)
        obs.channel = "sight"
        live.pulse(stamp)
        offer = live.admit(obs, sit.ingest(obs))
        if offer is None:
            result.append(item)
            continue
        if brief.sub == "league" and capture_age >= ttl(brief.phase):
            item["status"] = "stale"
        elif brief.sub == "league" and not cadence(brief.phase, offer.summary, talk=sit.talk,
                elapsed=stamp-last_offer, opening=last_offer < 0, same_phase=episode == announced_episode,
                identity_changed=brief.slots.get("hero") not in {"", "没看清", None, last_hero}):
            item["status"] = "cadence-held"
        elif hollow_company(offer.summary):
            item["status"] = "hollow"
        else:
            from app.modules.sight.service import bound_speech

            rule = brief.speak + brief.company + direction(brief.phase, offer.summary)
            item.update(status="offered", summary=offer.summary,
                        instruction=bound_speech(along_turn(sit.talk), line=offer.summary, rule=rule))
            last_offer, last_phase = stamp, brief.phase
            announced_episode = episode
            last_hero = brief.slots.get("hero") or last_hero
            sit.note_offered(False)
        live.candidate = None
        result.append(item)
    return result


async def real_dialogues(rows, limit, output):
    from sqlmodel import Session, select
    from app.db import engine
    from app.models import Character
    from app.services.settings_store import get_all
    from app.services.llm import SYSTEM_PROTOCOL

    with Session(engine) as database:
        conf = get_all(database)
        character = database.exec(select(Character).order_by(Character.id)).first()
        persona = character.persona if character else "你是小可爱，正在陪用户玩英雄联盟。"
    offered = [row for row in rows if row["status"] == "offered" and row["mode"] == "fresh-vision"]
    selected = []
    if limit:
        # Cover player identification, combat/death and final result, rather than
        # spending the entire model check on the first few lobby screenshots.
        for phase in ("load", "shop", "lane", "fight", "dead", "score"):
            matches = [r for r in offered if r.get("phase") == phase]
            if matches:
                selected.append(next((r for r in matches if r.get("hero") not in {"", "没看清", None}), matches[0]))
        selected = selected[:limit]
    unique = {r["id"]: r for r in selected}
    results = []
    for row in unique.values():
        started = time.time()
        pieces, errors = [], []
        messages = [{"role": "system", "content": persona + "\n" + SYSTEM_PROTOCOL + "\n" + row["summary"]},
                    {"role": "user", "content": row["instruction"]}]
        from app.modules.glance.game_director import grounded_reply

        reply = await grounded_reply(conf["llm"], messages, evidence=row["summary"], topic=row["id"])
        results.append({"id": row["id"], "summary": row["summary"], "instruction": row["instruction"],
                        "reply": reply["text"], "action": reply["action"], "attempts": reply["attempts"],
                        "errors": [error for attempt in reply["attempts"] for error in attempt["errors"]],
                        "performance": reply["performance"], "generation_ms": int((time.time()-started)*1000),
                        "playback": "not-tested"})
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=Path("data/glance-lab"))
    parser.add_argument("--fresh", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/companion-eval/history.json"))
    parser.add_argument("--llm", type=int, default=0)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in args.archive.rglob("*.json") if p.name != "keep.json"]
    rows = sorted((r for r in rows if r.get("at") and r.get("id")), key=lambda r: (r["at"], r["id"]))
    fresh = {r["id"]: r for r in json.loads(args.fresh.read_text(encoding="utf-8"))} if args.fresh else {}
    result = replay(rows, fresh)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    from collections import Counter

    report = {"summary": {"records": len(result), "fresh_vision": len(fresh),
                          "status": dict(Counter(r["status"] for r in result)),
                          "note": "Historical window identity is inferred when missing; no physical playback is simulated."}, "rows": result}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    if args.llm:
        asyncio.run(real_dialogues(result, args.llm, args.output.with_name("real-dialogues.json")))


if __name__ == "__main__":
    main()
