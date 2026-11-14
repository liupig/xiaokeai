from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "python-packages"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import mmd_tools

mmd_tools.register()

from motionlab.blender_pipeline.retarget import convert_file


def arguments():
    parser = argparse.ArgumentParser(description="无头 Blender：Mixamo FBX 批量转 MMD VMD")
    parser.add_argument("inputs", nargs="+", type=Path, help="FBX 文件或目录")
    parser.add_argument("--model", required=True, type=Path, help="目标 PMX 模型")
    parser.add_argument("--output", required=True, type=Path, help="VMD 输出目录")
    parser.add_argument("--recursive", action="store_true", help="递归搜索输入目录")
    parser.add_argument("--allow-root-motion", action="store_true", help="保留水平位移，默认原地播放")
    parser.add_argument("--limit", type=int, default=0, help="每个输入目录最多转换多少个，0 为不限")
    parser.add_argument("--fail-fast", action="store_true", help="首个失败后立即停止")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def collect(inputs, recursive, limit):
    files = []
    for source in inputs:
        if source.is_file() and source.suffix.lower() == ".fbx":
            files.append(source)
        elif source.is_dir():
            found = source.rglob("*.fbx") if recursive else source.glob("*.fbx")
            files.extend(sorted(path for path in found if path.is_file()))
    files = list(dict.fromkeys(path.resolve() for path in files))
    return files[:limit] if limit > 0 else files


def main():
    args = arguments()
    files = collect(args.inputs, args.recursive, args.limit)
    if not files:
        raise ValueError("输入中没有 FBX 文件")
    succeeded = []
    failed = []
    for index, source in enumerate(files, 1):
        output = args.output / f"{source.stem}.vmd"
        try:
            info = convert_file(
                source.resolve(), args.model.resolve(), output.resolve(),
                in_place=not args.allow_root_motion,
                progress=lambda done, total: print(f"  帧 {done}/{total}", flush=True),
            )
            succeeded.append({"input": str(source), "output": str(output), **info})
            print(f"[{index}/{len(files)}] 完成 {source.name} -> {output}", flush=True)
        except Exception as error:
            failed.append({"input": str(source), "error": str(error)})
            print(f"[{index}/{len(files)}] 失败 {source.name}: {error}", file=sys.stderr, flush=True)
            traceback.print_exc()
            if args.fail_fast:
                break
    print("XIAOKE_CONVERSION_SUMMARY=" + json.dumps({
        "succeeded": succeeded, "failed": failed,
    }, ensure_ascii=False), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
