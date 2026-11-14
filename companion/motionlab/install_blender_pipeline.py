from __future__ import annotations

import argparse
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLENDER_VERSION = "4.5.16"
BLENDER_URL = f"https://mirrors.tuna.tsinghua.edu.cn/blender/release/Blender4.5/blender-{BLENDER_VERSION}-windows-x64.zip"
MMD_URL = "https://github.com/MMD-Blender/blender_mmd_tools/releases/download/v4.5.14/mmd_tools-v4.5.14-bl4.2.zip"


def download(url: str, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        return
    print(f"下载 {url}", flush=True)
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
            print(f"  {out.tell() / 1024 / 1024:.0f} MiB", end="\r", flush=True)
    print()


def install(check=False):
    tools = ROOT / "tools"
    blender_dir = tools / "blender" / f"blender-{BLENDER_VERSION}-windows-x64"
    blender = blender_dir / "blender.exe"
    if check:
        if not blender.is_file() or not (tools / "mmd_tools" / "__init__.py").is_file():
            raise SystemExit("Blender 管线尚未安装")
        subprocess.check_call([str(blender), "--version"])
        return
    downloads = tools / "_downloads"
    blender_zip = downloads / f"{blender_dir.name}.zip"
    mmd_zip = downloads / "mmd_tools.zip"
    download(BLENDER_URL, blender_zip)
    download(MMD_URL, mmd_zip)
    with zipfile.ZipFile(blender_zip) as archive:
        archive.extractall(tools / "blender")
    with zipfile.ZipFile(mmd_zip) as archive:
        archive.extractall(tools / "mmd_tools")
    wheel = next((tools / "mmd_tools" / "wheels").glob("opencc*.whl"))
    subprocess.check_call([
        str(blender_dir / "4.5" / "python" / "bin" / "python.exe"),
        "-m", "pip", "install", "--target", str(tools / "python-packages"), str(wheel),
    ])
    print(f"安装完成：{blender}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="安装无头 Blender + mmd_tools（项目内便携安装，无需管理员权限）")
    parser.add_argument("--check", action="store_true", help="只检查现有安装")
    args = parser.parse_args()
    install(args.check)
