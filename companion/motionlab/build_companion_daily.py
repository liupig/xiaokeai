from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from build_mixamo_pack import read_action_sheet

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "idle": [
        "Breathing_Idle", "Happy_Idle_2", "Sad_Idle_2", "Sad_Idle_3",
        "Idle", "Idle_6", "Arm_Stretching", "Look_Around_3",
        "Looking", "Looking_2", "Looking_Around", "Looking_Behind",
    ],
    "interact": [
        "Standing_Greeting", "Thankful", "Thinking",
        "Talking", "Talking_2", "Talking_4", "Talking_5", "Talking_7",
        "Agreeing_2", "Hard_Head_Nod", "Head_Nod_Yes",
        "Thoughtful_Head_Nod", "Thoughtful_Head_Shake", "Pointing_Forward",
        "Beckoning", "Happy", "Reacting", "Talking_At_Watercooler",
        "Texting", "Texting_While_Standing", "Drinking", "Sitting_Drinking",
    ],
    "greet": [],
    "dance": [],
}
SELECTED = [name for group in GROUPS.values() for name in group]
assert len(SELECTED) == 34 and len(set(SELECTED)) == 34


def main():
    parser = argparse.ArgumentParser(description="陪伴场景自然动作精选包")
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--input", type=Path, default=ROOT / "../_dl/Mixamo-Animations-Characters/animation_motion")
    parser.add_argument("--model", type=Path, default=ROOT / "assets/models/qingxiao/model.pmx")
    parser.add_argument("--output", type=Path, default=ROOT / "assets/motions/companion-daily")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    rows = read_action_sheet(args.xlsx)
    missing_excel = [name for name in SELECTED if name not in rows]
    missing_files = [name for name in SELECTED if not (args.input / f"{name}.fbx").is_file()]
    if missing_excel or missing_files:
        raise ValueError(f"清单缺失：{missing_excel}；文件缺失：{missing_files}")
    args.output.mkdir(parents=True, exist_ok=True)
    processes = []
    for worker in range(max(1, min(args.workers, 4))):
        chunk = SELECTED[worker::max(1, min(args.workers, 4))]
        if not chunk:
            continue
        command = [
            sys.executable, str(ROOT / "motionlab/blender_convert.py"),
            "--model", str(args.model), "--output", str(args.output),
            *(str(args.input / f"{name}.fbx") for name in chunk), "--fail-fast",
        ]
        log = (args.output / f"worker-{worker + 1}.log").open("w", encoding="utf-8")
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        processes.append((process, log))
    for process, log in processes:
        if process.wait():
            raise RuntimeError("转换失败，请检查 worker 日志")
        log.close()
    motions = []
    for category, names in GROUPS.items():
        for name in names:
            motions.append({
                "file": f"{name}.vmd", "label": rows[name].get("A") or name,
                "category": category, "seconds": float(rows[name]["D"]),
                "description": rows[name].get("E", ""),
                "source": rows[name]["H"].replace("/animation/", "/animation_motion/"),
            })
    (args.output / "manifest.json").write_text(json.dumps({
        "pack": "companion-daily", "version": 1, "motions": motions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for log in args.output.glob("worker-*.log"):
        log.unlink()
    print(f"自然动作精选包完成：{len(motions)} 个 VMD", flush=True)


if __name__ == "__main__":
    main()
