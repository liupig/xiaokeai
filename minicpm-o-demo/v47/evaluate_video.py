"""Content evaluation on an archived chronological game sequence (no capture)."""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path


QUESTION = (
    "只根据输入画面回答以下问题，不要补剧情。输入可能只有一帧，无法判断变化就写无法判断。"
    "1.这是哪个游戏，处于什么阶段？"
    "2.玩家控制的角色是哪个英雄？看不清就说不确定。"
    "3.按开始、交互过程、最后状态描述玩家与敌方英雄的交互，不要用进攻或防守之类套话。"
    "4.玩家血量从开始到最后如何变化？能读出数字就写，读不出只说趋势。"
    "5.最后玩家和敌方英雄是否死亡？有无明确击杀证据？"
    "6.玩家最后在防御塔的哪个方向？不要把小兵当英雄。每题一句，中文回答。"
)


def main():
    import engine
    from PIL import Image

    output = Path(__file__).parent / "tmp" / "video-quality.json"
    originals = []
    for i in range(1, 5):
        with Image.open(output.parent / f"reel-{i}.jpg") as image:
            originals.append(image.convert("RGB"))
    print("Loading model", flush=True)
    engine.load()
    rows = []
    cases = [("single", "16x", 960, False), ("images", "16x", 960, False),
             ("video", "16x", 960, False), ("images", "4x", 1920, False),
             ("video", "4x", 1920, False), ("video", "4x", 1920, True)]
    for mode, downsample, edge, reverse in cases:
        images = [engine._fit(im, edge) for im in originals]
        if reverse:
            images.reverse()
        row = dict(mode=mode, downsample=downsample, edge=edge, reversed=reverse)
        print(json.dumps(row), flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix="quality-video-") as directory:
                path = engine._write_clip(images, path=Path(directory) / "clip.mp4") if mode == "video" else None
                text = engine.describe(images[-1], QUESTION, downsample=downsample,
                                       max_slice_nums=1, max_new_tokens=300,
                                       frames=images if mode == "images" else None,
                                       video_path=path, do_sample=False, stream=False,
                                       preface=False, stop_event=threading.Event())
            row.update(ok=True, text=text, profile=dict(engine._last_profile))
        except Exception as exc:
            row.update(ok=False, error=str(exc))
        rows.append(row)
        output.write_text(json.dumps(dict(question=QUESTION, runs=rows), ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(row, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
