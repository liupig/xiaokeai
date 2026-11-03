"""Real CPU OCR checks; generated language cards are labelled, not game accuracy."""
from pathlib import Path
import json
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont
import psutil
from app.modules.sight import rapid_text, screen_text


def compact(text):
    return re.sub(r"[^\w]", "", text).casefold()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    folder = Path("data/ocr-eval")
    folder.mkdir(parents=True, exist_ok=True)
    samples = [
        ("zh", "船就要开了，快上来", "msyh.ttc"),
        ("en", "The ship is leaving. Come aboard.", "arial.ttf"),
        ("ja", "船が出るよ、早く乗って", "YuGothM.ttc"),
        ("ko", "배가 곧 떠나요. 빨리 타세요.", "malgun.ttf"),
    ]
    process = psutil.Process()
    baseline = process.memory_info().rss
    checks = []
    for lang, line, font in samples:
        image = Image.new("RGB", (1100, 260), "white")
        ImageDraw.Draw(image).text((60, 100), line, font=ImageFont.truetype("C:/Windows/Fonts/"+font, 42), fill="black")
        image.save(folder / (lang + ".png"))
        started = time.perf_counter()
        rows = rapid_text.read(image)
        seen = " ".join(row["text"] for row in rows)
        check = {"language": lang, "source": "generated-print-card", "expected": line, "seen": seen,
                 "passed": compact(line) in compact(seen), "ms": round((time.perf_counter()-started)*1000), "rows": rows}
        checks.append(check)
        print(json.dumps({k:v for k,v in check.items() if k != "rows"}, ensure_ascii=False), flush=True)
    real = []
    paths = ["data/glance-lab/2026-11-02/g20261102165041044-0307-c7.jpg",
             "data/glance-lab/2026-11-02/g20261102165718442-0355-c7.jpg",
             "data/glance-lab/2026-11-01/g20261101125147523-0006-c7.jpg"]
    for path in paths:
        image = Image.open(path).convert("RGB")
        started = time.perf_counter()
        native = screen_text._read_native(image)
        native_ms = round((time.perf_counter()-started)*1000)
        started = time.perf_counter()
        rapid = rapid_text.read(image)
        rapid_ms = round((time.perf_counter()-started)*1000)
        real.append({"path": path, "source": "archived-image", "windows_ms": native_ms, "rapid_ms": rapid_ms,
                     "windows": native, "rapid": rapid, "game_facts": screen_text.facts(rapid, image_size=image.size)})
        print(json.dumps({"image":path,"windows_ms":native_ms,"rapid_ms":rapid_ms,"rapid_lines":len(rapid)}, ensure_ascii=False), flush=True)
    providers = [rapid_text._engine.text_det.session.session.get_providers(),
                 rapid_text._engine.text_rec.session.session.get_providers(),
                 rapid_text._korean.text_rec.session.session.get_providers()]
    report = {"language_checks": checks, "real_images": real, "providers": providers,
              "process_rss_before_mb": round(baseline/1024**2, 1),
              "process_rss_after_mb": round(process.memory_info().rss/1024**2, 1)}
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert all(check["passed"] for check in checks)
    assert all(provider == ["CPUExecutionProvider"] for provider in providers)
    assert "继续游戏" in real[1]["game_facts"]


if __name__ == "__main__":
    main()
