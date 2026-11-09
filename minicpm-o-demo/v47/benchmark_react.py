import argparse
import json
import math
import re
import time
from pathlib import Path

import engine


SUBTITLES = [
    "船马上就要开了", "你为什么不告诉他真相", "别回头，继续往前走",
    "原来你一直都在等我", "这把钥匙只能开一扇门", "你真的以为我会害怕吗",
    "妈妈，我今天交到朋友了", "对不起，我来晚了", "这次换我保护你",
    "他从来没有离开过这里", "你还记得第一次见面的地方吗", "别说话，听我解释",
    "我们一定会再见的", "这条路怎么越来越黑了", "你刚才是不是笑了",
    "以后不要再一个人扛着", "门后面好像有声音", "我已经不是小孩子了",
    "这就是你最后的答案吗", "天亮了，我们该走了",
]
MOODS = {"紧张", "搞笑", "温馨", "悲伤", "燃", "尴尬", "无聊", "平静"}


def prompt(subtitle):
    return (
        "你是小可爱，正和他一起看这部电影。你说话自然、简短，像坐在旁边的朋友。"
        "你温柔但不刻意讨好，有真实反应，不复述剧情，不编造画面。\n"
        f"刚刚片子里说：「{subtitle}」\n"
        "严格只输出三行：\n"
        "情绪：（紧张/搞笑/温馨/悲伤/燃/尴尬/无聊/平静，选一个）\n"
        "值不值得说：（说/不说）\n"
        "台词：（一句不超过25字的口语；不说就留空）"
    )


def valid(raw):
    fields = {}
    for label in ("情绪", "值不值得说", "台词"):
        match = re.search(rf"^\s*{label}\s*[：:]\s*(.*)\s*$", raw, re.M)
        if not match:
            return False
        fields[label] = match.group(1).strip()
    return (
        fields["情绪"] in MOODS
        and fields["值不值得说"] in {"说", "不说"}
        and len(re.sub(r"\s+", "", fields["台词"])) <= 25
    )


def percentile(rows, ratio):
    return sorted(rows)[max(0, math.ceil(len(rows) * ratio) - 1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("tmp/react-benchmark.json"))
    args = parser.parse_args()
    engine.load()
    engine.describe(None, prompt("预热一句"), downsample="16x", max_slice_nums=1,
                    max_new_tokens=80, do_sample=False, stream=False, preface=False)
    rows = []
    for index in range(args.count):
        subtitle = SUBTITLES[index % len(SUBTITLES)]
        started = time.monotonic()
        raw = engine.describe(None, prompt(subtitle), downsample="16x", max_slice_nums=1,
                              max_new_tokens=80, do_sample=False, stream=False, preface=False)
        elapsed = round((time.monotonic() - started) * 1000)
        row = {"index": index + 1, "subtitle": subtitle, "ms": elapsed,
               "valid": valid(raw), "raw": raw}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    times = [row["ms"] for row in rows]
    stability = sum(row["valid"] for row in rows) / len(rows)
    summary = {
        "count": len(rows),
        "p50_ms": percentile(times, 0.5),
        "p90_ms": percentile(times, 0.9),
        "format_stability": stability,
        "passes": percentile(times, 0.9) <= 3000 and stability >= 0.95,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
