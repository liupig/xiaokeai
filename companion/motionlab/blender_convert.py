from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLENDER = ROOT / "tools" / "blender" / "blender-4.5.16-windows-x64" / "blender.exe"


def main():
    parser = argparse.ArgumentParser(description="调用无头 Blender 执行 Mixamo → VMD 转换")
    parser.add_argument("--blender", type=Path, default=Path(os.environ.get("BLENDER_BIN", DEFAULT_BLENDER)))
    args, passthrough = parser.parse_known_args()
    if not args.blender.is_file():
        parser.error(f"找不到 Blender：{args.blender}")
    command = [
        str(args.blender), "--background", "--factory-startup",
        "--python", str(ROOT / "motionlab" / "blender_pipeline" / "cli.py"),
        "--", *passthrough,
    ]
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
