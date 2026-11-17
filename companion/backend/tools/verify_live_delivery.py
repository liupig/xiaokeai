"""直播交付验收：跑真实状态机回归并导出机器可读报告，不访问真实观众。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "test_live_delivery.py", "test_live_idiom.py", "test_live_bili_login.py", "test_live_bili_web.py",
    "test_live_host.py", "test_live_attention.py", "test_protocol_edges.py", "test_live_lab.py",
    # 个人聊天相关资产、陪玩与陪看隔离回归。
    "test_tavern.py", "test_tavern_runtime.py", "test_glance_situation.py", "test_glance_journal.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT.parent / "artifacts" / "live-delivery-acceptance.json")
    args = parser.parse_args()
    started = time.perf_counter()
    command = [sys.executable, "-m", "pytest", *(f"tests/{name}" for name in TESTS),
               "-q", "-p", "no:cacheprovider", "--basetemp", "data/tmp/pytest-live-delivery-acceptance"]
    env = dict(__import__("os").environ)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=env,
                            encoding="utf-8", errors="replace")
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr.strip()
    report = {
        "product": "live-show-engine-v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ok": result.returncode == 0,
        "summary": summary,
        "elapsed_sec": round(time.perf_counter() - started, 2),
        "coverage": {
            "bilibili_open_and_web": True,
            "anonymous_and_qr_login": True,
            "audience_attribution": True,
            "deterministic_idiom_turns": True,
            "persistent_session_receipts": True,
            "playback_ack": True,
            "sparse_room_fast_path": True,
            "personal_tavern_and_watch_regression": True,
            "real_room_soak_test": "separate_operator_acceptance",
        },
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-2000:],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
