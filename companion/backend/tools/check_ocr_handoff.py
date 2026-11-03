"""Feed fresh real-model/OCR results into the production companion offer gates."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.sight import service
from app.modules.glance.situation import Situation, parse_observation
from app.modules.glance.watch import WatchSession
from app.modules.glance.media_director import cadence, bind_context


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = json.loads(Path("data/ocr-eval/fresh-vision.json").read_text(encoding="utf-8"))
    report = []
    for row in rows:
        service.reset()
        if row["kind"] == "game":
            source = ("League of Legends.exe", "League of Legends", "League of Legends")
            service.commit(*source, "画面：局内HUD可见")
        else:
            source = ("chrome.exe", "抖音", "抖音")
        brief = service.commit(*source, row["result"])
        sit = Situation()
        watch = WatchSession(sit)
        stamp = time.time()
        watch.pulse(stamp)
        obs = parse_observation(brief.handoff, timestamp=stamp)
        offer = watch.admit(obs, sit.ingest(obs))
        if row["kind"] != "game":
            if not cadence(brief.kind, elapsed=99, opening=True, talk="normal", playback=brief.slots.get("playback", "")):
                offer = None
            elif offer:
                bind_context(offer, brief.public())
        report.append({"id": row["id"], "phase": brief.phase, "handoff": brief.handoff,
                       "offered": offer is not None, "summary": offer.summary if offer else ""})
    assert report[0]["phase"] == "score" and report[0]["offered"]
    assert "返回于" not in report[0]["summary"]
    assert not report[1]["offered"]
    assert report[2]["offered"]
    Path("data/ocr-eval/handoff.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
