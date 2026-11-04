"""Measure the real local OCR and GPU overlap on one archived game image."""
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "companion/backend"))

import engine
from PIL import Image
from app.modules.sight.league import prompt


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[2] / "companion/backend"
    image = Image.open(root / "data/glance-lab/2026-11-02/g20261102165041044-0307-c7.jpg").convert("RGB")
    engine.load()
    opts = engine._clamp({"max_edge": 1920, "max_new_tokens": 240, "max_slice_nums": 9, "downsample": "4x"})
    opts.update(do_sample=False, stream=False, stop_on_label=False, preface=False)
    reader = engine._get_screen_reader()
    results = []
    for mode in ("warmup", "serial", "parallel", "serial", "parallel"):
        reader._ocr_cache.clear()
        started = time.perf_counter()
        future = engine._start_ocr(image) if mode == "parallel" else None
        gpu_start = time.perf_counter()
        text = engine._ask(image, None, prompt(), "", opts, stop_event=threading.Event(), once=True)
        gpu_ms = round((time.perf_counter()-gpu_start)*1000)
        if future:
            lines, status = engine._finish_ocr(future)
        else:
            lines, status = reader.read(image), "serial"
        result = engine._game_text(image, text, lines=lines)
        row = {"mode": mode, "gpu_ms": gpu_ms, "total_ms": round((time.perf_counter()-started)*1000),
               "ocr_status": status, "ocr_lines": len(lines), "result": result}
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    cache_start = time.perf_counter()
    cached = reader.read(image)
    report = {"runs": results, "exact_frame_cache_ms": round((time.perf_counter()-cache_start)*1000), "cached_lines": len(cached)}
    target = root / "data/companion-eval/ocr-performance.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
