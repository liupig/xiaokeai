"""一条命令回放四场虚构直播并导出可审计记录。播放回执是模拟值，报告明确标记。"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.modules.live.lab import LiveLab
from app.modules.live.lab_journal import LabJournal
from app.modules.live.lab_scenarios import SCENARIOS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "artifacts" / "live-lab-acceptance.json")
    args = parser.parse_args()
    reports = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="live-lab-") as temp:
        for scenario in SCENARIOS:
            lab = LiveLab(LabJournal(Path(temp) / "replay.sqlite3"))
            lab.start(scenario, background=False, now=1000)
            for now in range(1000, 1300):
                lab.step(now)
                if lab.host._turn:
                    lab.ack(lab.host._turn["id"], "completed", now=now + .5)
                if lab.state == "completed":
                    break
            report = lab.report()
            for key in ("unique_turn_ids", "unique_ack_ids", "no_unsettled_paid", "source_completed"):
                if not report["checks"][key]:
                    raise RuntimeError(f"{scenario}: {key} 未通过")
            reports.append(report)
            print(f"PASS {scenario}: {report['summary']['received']} events, {report['summary']['turns']} turns; audio receipts simulated")
            lab.stop()
    output = {"kind": "offline-replay-acceptance", "generated_at": time.time(),
              "wall_time_sec": round(time.perf_counter() - started, 3),
              "audio_verified": False, "real_model_verified": False,
              "note": "这份报告验证真实主持代码的回放流程；真实模型与真实语音请在彩排页面验收并导出另一份记录。", "runs": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {args.output.resolve()}")


if __name__ == "__main__":
    main()
