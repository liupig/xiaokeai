"""Shared continuous capture for XiaokeAI's on-demand video observations."""
import threading
import time
import re

from video_stream import LiveVideo

_lock = threading.Lock()
_live = None
_last_request = 0.0
_source = None
_generation = 0
_requests = threading.Lock()


def observe(engine, body):
    # FastAPI worker threads must never form a queue of obsolete observations.
    if not _requests.acquire(blocking=False):
        return dict(ok=True, text="", skipped=True, busy=True,
                    message="正在理解最新窗口，本次请求不排队")
    try:
        return _observe(engine, body)
    finally:
        _requests.release()


def request_close():
    global _generation
    _generation += 1
    threading.Thread(target=close, daemon=True, name="companion-video-stop").start()


def _expire():
    global _live
    while True:
        time.sleep(5)
        with _lock:
            if _live is not None and time.monotonic() - _last_request > 45:
                _live.close()
                _live = None


threading.Thread(target=_expire, daemon=True, name="companion-video-idle").start()


def close():
    global _live, _last_request
    with _lock:
        if _live is not None:
            _live.close()
            _live = None


def _observe(engine, body):
    global _live, _last_request, _source
    from observations import record, save_model_frames, save_raw_frame

    with _lock:
        generation = _generation
        _last_request = time.monotonic()
        engine.load()
        if generation != _generation:
            return dict(ok=True, text="", skipped=True, stale=True)
        source = (body.scene, getattr(body, "window_hwnd", 0), tuple(body.crop or []))
        if _live is not None and source != _source:
            _live.close()
            _live = None
        _source = source
        if _live is None or _live.error or not _live.thread.is_alive():
            if _live is not None:
                _live.close()
            _live = LiveVideo(
                lambda: engine._Screen(1),
                lambda image: engine._live_frame(image, 1, 960),
                fps=1, seconds=4,
                on_raw=lambda image, count: save_raw_frame(image, captured_total=count),
            ).start()
        deadline = time.monotonic() + 12
        while len(_live.latest()) < 4:
            if _live.error:
                raise _live.error
            if time.monotonic() > deadline:
                raise RuntimeError("连续视频窗口未就绪")
            time.sleep(0.05)
        clip = _live.latest()
        if time.monotonic() - clip[-1][0] > 2:
            _live.close()
            _live = LiveVideo(
                lambda: engine._Screen(1),
                lambda image: engine._live_frame(image, 1, 960),
                fps=1, seconds=4,
                on_raw=lambda image, count: save_raw_frame(image, captured_total=count),
            ).start()
            deadline = time.monotonic() + 12
            while len(_live.latest()) < 4:
                if _live.error:
                    raise _live.error
                if time.monotonic() > deadline:
                    raise RuntimeError("连续视频窗口未就绪")
                time.sleep(0.05)
            clip = _live.latest()
        images = [row[1] for row in clip]
        if body.crop and len(body.crop) == 4:
            # Coordinates are desktop pixels; model frames have already been fitted.
            raw_size = engine._grab_mss(1).size
            images = [engine._crop_frame(image, body.crop, {"left": 0, "top": 0},
                                         raw_size[0], raw_size[1]) for image in images]
        stamps = [row[0] for row in clip]
        scene = body.scene if body.scene in engine.SCENE_PROMPTS else "auto"
        prompt = (
            "按时间顺序理解这一段连续视频，只记录已发生且能确认的事实。"
            "看不清就留空；封面、推荐卡片和广告不等于正在播放或正在对局。"
            "不将主播、角色或镜头中心当用户；不从历史推断当前事件。\n"
            + engine.SCENE_PROMPTS[scene]
        )
        # Conversation history and task instructions are not pixels. Supplying
        # them here caused the small model to copy old scene facts and task names.
        # Legacy scene prompts request independent numbered image descriptions.
        # Native video uses the scene policy above and a single concise contract.
        prompt += "\n只概括最后时刻的当前状态和本段一个关键变化，每项最多25字。不要逐帧解说，不写第一张、第二张，不分析推理过程。"
        # Keep the established XiaokeAI fact parser and scene state machines.
        prompt += "\n按现有场景要求输出可确认事实；历史仅供对比，不作为当前事实证据。"
        prompt += "\n只输出两行：画面：当前实际可见的主体和动作\n经过：本段明确的变化，没有则留空。不要输出标题、阶段、原文或任务指令。"
        paths = save_model_frames(images, frame_ids=[row[2] for row in clip])
        started = time.monotonic()
        text = engine.describe(images[-1], prompt, frames=images,
                               video_timestamps=stamps, downsample="16x",
                               max_slice_nums=1, max_new_tokens=48,
                               do_sample=False, stream=False, preface=False)
        if generation != _generation:
            return dict(ok=True, text="", skipped=True, stale=True,
                        message="陪看已停止，丢弃进行中的视觉结果")
        elapsed = round((time.monotonic() - started) * 1000)
        _last_request = time.monotonic()
        observed_at = time.time() - (time.monotonic() - stamps[-1])
        stats = dict(scene=scene, input_mode="live_video", video_frames=len(images),
                     video_span=stamps[-1] - stamps[0], observed_at=observed_at,
                     channel="continuous", frames=len(images), ms=elapsed,
                     downsample="16x", slices=1)
        record(text=text, prompt=prompt, elapsed_ms=elapsed, stats=stats,
               model_frames=paths, raw_frames=[row[3] for row in clip],
               frame_offsets_s=[stamp - stamps[0] for stamp in stamps])
        # A stable scene still has usable facts. Let the companion deduplicate;
        # do not erase a whole observation because its final field says unchanged.
        unchanged = text.strip().strip("。") == "没变"
        return dict(ok=True, text=text, skipped=unchanged,
                    elapsed_ms=elapsed, **stats)
