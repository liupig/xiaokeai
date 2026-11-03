"""Apply the production OCR verifier to a completed image-model replay."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app.modules.sight.screen_text import facts, read, verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    checked = []
    for index, row in enumerate(rows):
        if row.get("ok") and row.get("images"):
            image = Image.open(row["images"][-1]).convert("RGB")
            lines = read(image)
            raw = row["result"]
            text = verify(raw, lines)
            ocr = facts(lines, image_size=image.size)
            if ocr:
                text += "\n" + ocr
            row = {**row, "result": text, "ocr_verified": bool(lines)}
        checked.append(row)
        args.output.write_text(json.dumps(checked, ensure_ascii=False, indent=2), encoding="utf-8")
        if (index + 1) % 20 == 0 or index + 1 == len(rows):
            print(f"OCR verified {index+1}/{len(rows)}", flush=True)


if __name__ == "__main__":
    main()
