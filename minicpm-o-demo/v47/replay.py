"""Re-infer archived screenshots without capturing or touching the desktop."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "companion" / "backend"))
    import engine
    from PIL import Image
    from app.modules.sight.league import prompt
    from app.modules.sight.media import prompt as media_prompt
    from app.modules.sight.screen_text import read, facts, verify

    jobs = json.loads(args.manifest.read_text(encoding="utf-8"))
    print(json.dumps({"stage": "loading", "count": len(jobs)}), flush=True)
    engine.load()
    results = []
    for job in jobs:
        started = time.time()
        try:
            images = [Image.open(path).convert("RGB") for path in job["images"]]
            opts = engine._clamp({"max_edge": 1920, "max_new_tokens": 240,
                                  "max_slice_nums": 9, "downsample": "4x"})
            opts.update(do_sample=False, stream=False, stop_on_label=False, preface=False)
            kind = job.get("kind", "game")
            question = media_prompt(kind) if kind in {"movie", "music", "video"} else prompt()
            ocr_job = engine._start_ocr(images[-1])
            text = engine._ask(images[-1], None,
                               question, "", opts, stop_event=threading.Event(), once=True)
            lines, ocr_status = engine._finish_ocr(ocr_job)
            text = engine._media_text(images[-1], text, question, lines=lines) if kind in {"movie", "music", "video"} else engine._game_text(images[-1], text, lines=lines)
            ocr = ""
            for previous in images[:-1] if kind == "game" else []:
                earlier = engine._game_text(previous)
                # Match result is durable; an old respawn countdown is not.
                stable = [line for line in earlier.splitlines() if line.startswith("结果：")]
                if stable:
                    ocr += "\n" + "\n".join(stable)
            text += ("\n" + ocr) if ocr else ""
            row = {**job, "ok": True, "result": text, "ms": int((time.time() - started) * 1000), "ocr_status": ocr_status,
                   "ocr_engine": sorted({line.get("engine", "unknown") for line in lines})}
        except Exception as exc:
            row = {**job, "ok": False, "error": str(exc)}
        results.append(row)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
