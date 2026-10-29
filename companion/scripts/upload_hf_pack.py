#!/usr/bin/env python3
"""把一对 A/B 体验包传到 Hugging Face 数据集。

2026-10-28 那一对已经在仓库根目录，不要再用这个脚本重传。
以后每一次都先建时间戳文件夹，再把文件放进去，例如：

  20261029120000/xiaoke-ai-agent-A-20261029120000.7z
  20261029120000/xiaoke-ai-agent-B-20261029120000.7z

Token 读 HF_TOKEN，顺序是环境变量、companion/scripts/.env、companion/.env。
不要把 token 写进命令行。

用法（在 companion 目录）:

  backend\\.venv\\Scripts\\python.exe scripts\\upload_hf_pack.py ^
    E:\\BingCode\\bingGames\\xiaoke-ai-agent-A-20261029120000.7z ^
    E:\\BingCode\\bingGames\\xiaoke-ai-agent-B-20261029120000.7z
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
STAMP_RE = re.compile(r"(20\d{12})")
DEFAULT_REPO = "liupigai/xiaokeai"


def load_env_files() -> None:
    for env_path in (SCRIPT_DIR / ".env", ROOT / ".env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


def stamp_of(path: Path) -> str:
    match = STAMP_RE.search(path.name)
    if not match:
        raise SystemExit(f"文件名里没有 14 位时间戳，无法建文件夹: {path.name}")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="上传体验包到 Hugging Face，每个时间戳一个文件夹")
    parser.add_argument("files", nargs="+", type=Path, help="要上传的 7z，同一时间戳放进同一个文件夹")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"数据集仓库，默认 {DEFAULT_REPO}")
    args = parser.parse_args()

    load_env_files()
    token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
    if not token:
        raise SystemExit("缺少 HF_TOKEN。写到 companion/scripts/.env 或 companion/.env，不要提交。")

    files = []
    for path in args.files:
        path = path.resolve()
        if not path.is_file():
            raise SystemExit(f"找不到文件: {path}")
        files.append(path)

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(repo_id=args.repo, repo_type="dataset", private=False, exist_ok=True)

    for path in files:
        stamp = stamp_of(path)
        path_in_repo = f"{stamp}/{path.name}"
        remote = api.get_paths_info(args.repo, [path_in_repo], repo_type="dataset")
        if remote and getattr(remote[0], "size", None) == path.stat().st_size:
            print(f"skip {path_in_repo} ({path.stat().st_size} bytes)", flush=True)
            continue
        print(f"upload {path.name} -> {args.repo}/{path_in_repo}", flush=True)
        url = api.upload_file(
            path_or_fileobj=str(path),
            path_in_repo=path_in_repo,
            repo_id=args.repo,
            repo_type="dataset",
            commit_message=f"Add {stamp}/{path.name}",
        )
        print(url, flush=True)
        print(
            f"https://huggingface.co/datasets/{args.repo}/resolve/main/{path_in_repo}",
            flush=True,
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
