"""Benchmark actual continuous desktop capture while native video inference runs."""
import argparse
import json
import threading
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fps", nargs="+", type=int, default=[1, 2, 4, 6], choices=[1, 2, 4, 6])
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=4)
    parser.add_argument("--tokens", type=int, default=48)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "tmp" / "live-benchmark.json")
    args = parser.parse_args()
    import engine
    import torch
    from video_stream import LiveVideo

    output = args.output
    output.parent.mkdir(exist_ok=True)
    rows = []
    print("Loading model", flush=True)
    engine.load()
    for fps in args.fps:
        live = LiveVideo(lambda: engine._Screen(1), lambda im: engine._fit(im, 960), fps, args.seconds).start()
        last_end = 0
        try:
            # Startup only; subsequent samples come from recording during inference.
            deadline = time.monotonic()+15
            while len(live.latest()) < round(fps*args.seconds):
                if live.error:
                    raise live.error
                if time.monotonic() > deadline:
                    raise RuntimeError("Timed out waiting for screen frames")
                time.sleep(.05)
            for turn in range(args.turns):
                clip = live.latest()
                images = [item[1] for item in clip]
                stamps = [item[0] for item in clip]
                captured_before = live.count
                torch.cuda.reset_peak_memory_stats()
                started = time.monotonic()
                text = engine.describe(images[-1],
                    "用一句中文描述最近这段录屏里正在做什么，有什么变化。只写可见事实，不猜操作意图。",
                    frames=images, video_timestamps=stamps, downsample="16x",
                    max_slice_nums=1, max_new_tokens=args.tokens, do_sample=False,
                    stream=False, preface=False, stop_event=threading.Event())
                elapsed = time.monotonic()-started
                row = dict(fps=fps, turn=turn, capture_mode=live.mode,
                           actual_fps=round((len(clip)-1)/(stamps[-1]-stamps[0]),2),
                           frames=len(clip), span=round(stamps[-1]-stamps[0],2),
                           captured_during_inference=live.count-captured_before,
                           input_age=round(started-stamps[-1],2),
                           result_age=round(time.monotonic()-stamps[-1],2),
                           inference_seconds=round(elapsed,2),
                           skipped_frames=max(0, clip[0][2]-last_end-1) if last_end else 0,
                           peak_allocated_mib=round(torch.cuda.max_memory_allocated()/2**20),
                           profile=dict(engine._last_profile), text=text)
                last_end = clip[-1][2]
                rows.append(row)
                output.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
                print(json.dumps(row,ensure_ascii=True),flush=True)
        finally:
            live.close()


if __name__ == "__main__":
    main()
