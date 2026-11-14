from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from build_mixamo_pack import read_action_sheet

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    "待机/静态": "idle",
    "坐/蹲/卧/起身": "interact",
    "手势/交流": "interact",
    "舞蹈": "dance",
    "情绪姿态": "interact",
    "张望/观察": "idle",
    "社交/亲密": "interact",
}


def main():
    parser = argparse.ArgumentParser(description="转换 Excel 全部推荐动态动作，支持断点续跑")
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--input", type=Path, default=ROOT / "../_dl/Mixamo-Animations-Characters/animation_motion")
    parser.add_argument("--model", type=Path, default=ROOT / "assets/models/qingxiao/model.pmx")
    parser.add_argument("--output", type=Path, default=ROOT / "assets/motions/mixamo-recommended")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--overwrite", action="store_true", help="重定向算法更新后覆盖已有 VMD")
    args = parser.parse_args()
    rows = read_action_sheet(args.xlsx)
    recommended = [row for row in rows.values() if row.get("C") == "推荐"]
    missing = sorted(row["B"] for row in recommended if not (args.input / f"{row['B']}.fbx").is_file())
    pending = [row for row in recommended if (args.input / f"{row['B']}.fbx").is_file()
               and (args.overwrite or not (args.output / f"{row['B']}.vmd").is_file())]
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"推荐 {len(recommended)}；静态排除 {len(missing)}；待转换 {len(pending)}", flush=True)
    worker_count = max(1, min(args.workers, 4, len(pending) or 1))
    logs = args.output / "_logs"
    logs.mkdir(exist_ok=True)
    processes = []
    for worker in range(worker_count):
        chunk = pending[worker::worker_count]
        if not chunk:
            continue
        command = [
            sys.executable, str(ROOT / "motionlab/blender_convert.py"),
            "--model", str(args.model), "--output", str(args.output),
            *(str(args.input / f"{row['B']}.fbx") for row in chunk),
        ]
        log = (logs / f"worker-{worker + 1}.log").open("w", encoding="utf-8")
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        processes.append((process, log))
    failed = []
    for process, log in processes:
        code = process.wait()
        log.close()
        if code:
            failed.append(code)
    manifest = []
    for row in recommended:
        if (args.input / f"{row['B']}.fbx").is_file():
            manifest.append({
                "file": f"{row['B']}.vmd",
                "label": row.get("A") or row["B"],
                "category": CATEGORIES[row["F"]],
                "seconds": float(row["D"]),
                "description": row.get("E", ""),
                "source": row["H"].replace("/animation/", "/animation_motion/"),
            })
    (args.output / "manifest.json").write_text(
        json.dumps({
            "pack": "mixamo-recommended", "version": 1,
            "static_poses_excluded": missing, "motions": manifest,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    converted = sum((args.output / row["file"]).is_file() for row in manifest)
    print(f"动作包完成：{converted}/{len(manifest)} 个 VMD；失败进程：{failed}", flush=True)
    return 1 if failed or converted != len(manifest) else 0


if __name__ == "__main__":
    raise SystemExit(main())
