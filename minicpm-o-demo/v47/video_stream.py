"""Continuous screen capture with a bounded latest-video window."""
from collections import deque
import threading
import time


class LiveVideo:
    def __init__(self, screen_factory, transform, fps=2, seconds=4, on_frame=None, on_raw=None):
        self.fps = fps
        self.seconds = seconds
        self.screen_factory = screen_factory
        self.transform = transform
        self.on_frame = on_frame
        self.on_raw = on_raw
        self.frames = deque(maxlen=max(2, int(fps * seconds) + 2))
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        self.error = None
        self.count = 0
        self.started = 0
        self.mode = ""

    def start(self):
        self.thread = threading.Thread(target=self._capture, daemon=True, name="live-video-capture")
        self.thread.start()
        return self

    def _capture(self):
        screen = self.screen_factory()
        try:
            self.mode = screen.open()
            self.started = time.monotonic()
            deadline = self.started
            while not self.stop.is_set():
                raw = screen.grab()
                if raw is not None:
                    image = self.transform(raw)
                    with self.lock:
                        self.count += 1
                        count = self.count
                    raw_path = self.on_raw(raw, count) if self.on_raw else ""
                    with self.lock:
                        self.frames.append((time.monotonic(), image, count, raw_path))
                    if self.on_frame:
                        self.on_frame(image)
                deadline += 1 / self.fps
                now = time.monotonic()
                if deadline < now:
                    deadline = now
                self.stop.wait(max(0, deadline - now))
        except Exception as exc:
            self.error = exc
        finally:
            screen.close()

    def latest(self):
        with self.lock:
            if not self.frames:
                return []
            end = self.frames[-1][0]
            # Keep a fixed number of frames; no pending inference queue.
            return [row for row in self.frames if end-row[0] < self.seconds][-max(2, round(self.fps*self.seconds)):]

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                raise RuntimeError("录屏线程未能停止")


def run(engine, opts):
    """Capture never pauses during generation; each call sees a recent video."""
    from observations import record, save_model_frames, save_raw_frame
    history = []
    last_end = 0
    last_inferred_at = 0.0
    last_visual_sig = None
    live = None
    failed = False
    revision = -1
    engine._set(running=True, message="正在加载连续视频理解")
    record(event="watch_started", reason="start", stats={
        "scene": opts.get("scene", "auto"), "capture_fps": opts["capture_fps"],
        "window_seconds": opts["window_seconds"], "max_edge": opts["max_edge"],
        "downsample": opts["downsample"], "max_new_tokens": opts["max_new_tokens"],
    })
    try:
        engine.load()
        live = LiveVideo(lambda: engine._Screen(opts["monitor"]),
                         lambda image: engine._live_frame(image, opts["monitor"], opts["max_edge"]),
                         opts["capture_fps"], opts["window_seconds"],
                         on_frame=lambda image: engine.publish(dict(type="preview", jpeg=engine._jpeg_b64(image, 960))),
                         on_raw=lambda raw, count: save_raw_frame(raw, captured_total=count)).start()
        ready_at = time.monotonic() + opts["window_seconds"]
        while not engine._stop.is_set():
            dynamic, current_revision = engine.watch_options()
            if current_revision != revision:
                revision = current_revision
                history.clear()
                last_end = 0
                last_inferred_at = 0.0
                last_visual_sig = None
                engine.publish(dict(type="scene_changed", scene=dynamic.get("scene", "auto")))
                record(event="scene_changed", reason="runtime_update", stats={
                    "scene": dynamic.get("scene", "auto"),
                    "scene_cadence_s": engine.scene_cadence(dynamic.get("scene", "auto")),
                    "watch_revision": revision,
                })
            if live.error:
                raise live.error
            clip = live.latest()
            if time.monotonic() < ready_at or len(clip) < 2 or clip[-1][2] <= last_end:
                if not clip and time.monotonic() > ready_at + 10:
                    raise RuntimeError("连续录屏没有返回画面")
                engine._stop.wait(0.05)
                continue
            scene = dynamic.get("scene", "auto")
            if last_inferred_at and time.monotonic() - last_inferred_at < engine.scene_cadence(scene):
                engine._stop.wait(0.05)
                continue
            previous_end = last_end
            images = [row[1] for row in clip]
            stamps = [row[0] for row in clip]
            sigs = [engine._sig(image) for image in images]
            if last_visual_sig is not None and not engine._span_changed(sigs, last_visual_sig):
                # A quiet desktop stays quiet without repeatedly asking the model.
                last_end = clip[-1][2]
                record(event="skipped", reason="static_visual_window", stats={
                    "scene": scene, "video_frames": len(clip),
                    "video_span": round(stamps[-1] - stamps[0], 2),
                    "captured_total": live.count, "input_mode": "live_video",
                }, frame_signature=sigs[-1].hex())
                engine._stop.wait(0.05)
                continue
            last_end = clip[-1][2]
            last_visual_sig = sigs[-1]
            preview = engine._jpeg_b64(images[-1], 960)
            engine.publish(dict(type="frame", jpeg=preview, width=images[-1].width, height=images[-1].height))
            started = time.monotonic()
            prompt = engine._build_watch_prompt(dynamic.get("prompt", ""), history, dynamic.get("compare_prev", True))
            text = engine.describe(images[-1], prompt, frames=images, video_timestamps=stamps,
                                   downsample=opts["downsample"], max_slice_nums=1,
                                   max_new_tokens=dynamic.get("max_new_tokens", opts["max_new_tokens"]), do_sample=False,
                                   stream=True, preface=False)
            if engine._stop.is_set():
                break
            stats = dict(capture_fps=opts["capture_fps"],
                         scene=scene,
                         scene_cadence_s=engine.scene_cadence(scene),
                         actual_fps=round((len(clip)-1)/(stamps[-1]-stamps[0]), 2),
                         video_frames=len(clip), video_span=round(stamps[-1]-stamps[0], 2),
                         input_age=round(started-stamps[-1], 2),
                         result_age=round(time.monotonic()-stamps[-1], 2),
                         skipped_frames=max(0, clip[0][2]-previous_end-1) if previous_end else 0,
                         captured_total=live.count, input_mode="live_video")
            engine._set(**stats, message=f"连续录屏 · {opts['capture_fps']} FPS · {live.mode}")
            elapsed_ms = round((time.monotonic()-started)*1000)
            last_inferred_at = time.monotonic()
            suppressed = engine._finish_text(text, history, elapsed_ms, preview)
            model_frames = save_model_frames(images, frame_ids=[row[2] for row in clip])
            record(text=text, prompt=prompt, suppressed=suppressed, stats=stats, elapsed_ms=elapsed_ms,
                   raw_frames=[row[3] for row in clip], model_frames=model_frames,
                   frame_ids=[row[2] for row in clip],
                   frame_offsets_s=[round(stamp - stamps[0], 4) for stamp in stamps])
            engine.publish(dict(type="video_stats", **stats))
            engine._stop.wait(opts["min_gap"])
    except Exception as exc:
        failed = True
        record(event="error", reason="watch_exception", text=str(exc))
        engine._set(message=str(exc))
        engine.publish(dict(type="error", message=str(exc)))
    finally:
        if live:
            try:
                live.close()
            except Exception as exc:
                failed = True
                engine._set(message=str(exc))
                engine.publish(dict(type="error", message=str(exc)))
        record(event="watch_stopped", reason="error" if failed else "user_or_normal_stop",
               stats={"captured_total": live.count if live else 0})
        engine._set(running=False, **({} if failed else dict(message="已停止")))
        engine.publish(dict(type="status", **engine.status()))
