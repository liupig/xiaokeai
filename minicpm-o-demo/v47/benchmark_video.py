"""Compare identical archived frames as single image, images and native video."""
from __future__ import annotations

import argparse
import json
import tempfile
import threading
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="Frames in chronological order")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prompt", default="按时间顺序描述画面中实际发生的变化，写清开始、过程和最后状态。看不出的动作不要猜。")
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    if len(args.images) < 2 or args.repeats < 1:
        parser.error("At least two chronological frames and one repeat are required")
    import engine
    import torch
    from PIL import Image

    images = []
    for path in args.images:
        with Image.open(path) as image:
            frame = image.convert("RGB")
            frame.thumbnail((960, 960))
            images.append(frame)
    images = engine._even(images, 6)
    engine.load()
    rows = []
    with tempfile.TemporaryDirectory(prefix="minicpm-benchmark-") as directory:
        started = time.perf_counter()
        clip = engine._write_clip(images, path=Path(directory) / "clip.mp4")
        encode_ms = round((time.perf_counter() - started) * 1000)
        for repeat in range(args.repeats):
            # Reverse order on alternating repeats to expose first-run overhead.
            modes = ["single", "images", "video"]
            if repeat % 2:
                modes.reverse()
            for mode in modes:
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                started = time.perf_counter()
                try:
                    text = engine.describe(
                        images[-1], args.prompt, downsample="16x", max_slice_nums=1,
                        max_new_tokens=160, frames=images if mode == "images" else None,
                        video_path=clip if mode == "video" else None,
                        do_sample=False, stream=False, preface=False,
                        stop_event=threading.Event(),
                    )
                    torch.cuda.synchronize()
                    row = dict(mode=mode, repeat=repeat, ok=True, text=text,
                               elapsed_ms=round((time.perf_counter()-started)*1000),
                               peak_allocated_mib=round(torch.cuda.max_memory_allocated()/2**20),
                               peak_reserved_mib=round(torch.cuda.max_memory_reserved()/2**20),
                               profile=dict(engine._last_profile))
                except Exception as exc:
                    row = dict(mode=mode, repeat=repeat, ok=False, error=str(exc))
                rows.append(row)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(dict(
                    source_frames=[str(path.resolve()) for path in args.images],
                    selected_frames=len(images), fps=2, clip_encode_ms=encode_ms,
                    prompt=args.prompt, runs=rows,
                ), ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(row, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
